#!/usr/bin/env python3
"""tools/patch_firmware.py — Modular C/ASM Recompilation, Hook Injection & Repacker
for M-VAVE SMK-37 Pro Custom Firmware (JieLi AC791N / pi32v2)

Features:
1. Compiles custom C / Assembly sources using JieLi Clang (-target pi32v2)
2. Links with pi32v2-ld resolving all firmware symbols from firmware_structure.json
3. Injects compiled code into verified Flash code caves (default: 0x02096800)
4. Installs hooks (function replacement 'goto', call-site redirection 'call', or data pointers)
5. Automatically repacks into valid, encrypted (.fwsc) container ready for OTA flashing
6. Verifies binary integrity, CRCs, and branch displacements
"""
import os
import sys
import re
import struct
import subprocess
import json
import shutil
from pathlib import Path

# Paths
ROOT_DIR = Path(__file__).resolve().parent.parent
TOOLCHAIN_DIR = ROOT_DIR / "toolchain" / "C$" / "JL" / "pi32" / "bin"
CLANG_EXE = TOOLCHAIN_DIR / "clang.exe"
LD_EXE = TOOLCHAIN_DIR / "pi32v2-ld.exe"
OBJDUMP_EXE = TOOLCHAIN_DIR / "llvm-objdump.exe"

STOCK_FWSC = ROOT_DIR / "smk-37-pro-docs" / "firmware" / "smk37pro" / "SMK-37_Pro_016.fwsc"
DEFAULT_APP_BIN = ROOT_DIR / "firmware_work" / "v16_unpacked" / "files" / "app.bin"
DEFAULT_DB = ROOT_DIR / "firmware_work" / "analysis" / "firmware_structure.json"

FLASH_BASE = 0x02000000
DEFAULT_CAVE_ADDR = 0x02096800  # 1440 bytes of continuous zero cave
DEFAULT_CAVE_MAX_SIZE = 1400

# Branch instruction encoders for pi32v2
def encode_goto(from_addr: int, to_addr: int) -> bytes:
    """Encode a 32-bit unconditional 'goto target' instruction in pi32v2."""
    disp = to_addr - from_addr
    # Format: opcode 0xEA, relative displacement
    # We use pi32v2-ld to assemble exact encoding safely
    asm_content = f".text\n.global _hook\n_hook:\n  goto target_func\n"
    tmp_s = ROOT_DIR / "firmware_work" / "_tmp_goto.S"
    tmp_o = ROOT_DIR / "firmware_work" / "_tmp_goto.o"
    tmp_bin = ROOT_DIR / "firmware_work" / "_tmp_goto.bin"
    tmp_s.write_text(asm_content)
    subprocess.run([str(CLANG_EXE), "-target", "pi32v2", "-c", str(tmp_s), "-o", str(tmp_o)], check=True)
    subprocess.run([
        str(LD_EXE), f"-Ttext=0x{from_addr:08x}", f"--defsym=target_func=0x{to_addr:08x}",
        "--oformat=binary", str(tmp_o), "-o", str(tmp_bin)
    ], check=True)
    encoded = tmp_bin.read_bytes()
    for p in [tmp_s, tmp_o, tmp_bin]:
        if p.exists(): p.unlink()
    return encoded[:4]

def encode_call(from_addr: int, to_addr: int) -> bytes:
    """Encode a 32-bit 'call target' instruction in pi32v2."""
    asm_content = f".text\n.global _hook\n_hook:\n  call target_func\n"
    tmp_s = ROOT_DIR / "firmware_work" / "_tmp_call.S"
    tmp_o = ROOT_DIR / "firmware_work" / "_tmp_call.o"
    tmp_bin = ROOT_DIR / "firmware_work" / "_tmp_call.bin"
    tmp_s.write_text(asm_content)
    subprocess.run([str(CLANG_EXE), "-target", "pi32v2", "-c", str(tmp_s), "-o", str(tmp_o)], check=True)
    subprocess.run([
        str(LD_EXE), f"-Ttext=0x{from_addr:08x}", f"--defsym=target_func=0x{to_addr:08x}",
        "--oformat=binary", str(tmp_o), "-o", str(tmp_bin)
    ], check=True)
    encoded = tmp_bin.read_bytes()
    for p in [tmp_s, tmp_o, tmp_bin]:
        if p.exists(): p.unlink()
    return encoded[:4]

def compile_source(
    src_path: Path,
    cave_addr: int = DEFAULT_CAVE_ADDR,
    extra_cflags: list = None,
    extra_syms: dict = None,
    db_path: Path = DEFAULT_DB
) -> tuple[bytes, Path]:
    """Compile custom C/ASM file and link at cave_addr."""
    if not CLANG_EXE.exists() or not LD_EXE.exists():
        raise FileNotFoundError(f"JieLi pi32 toolchain not found at {TOOLCHAIN_DIR}")

    out_o = src_path.with_suffix(".o")
    out_bin = src_path.with_suffix(".bin")
    out_elf = src_path.with_suffix(".elf")

    # 1. Compile
    cflags = ["-target", "pi32v2", "-O2", "-c"]
    if extra_cflags:
        cflags.extend(extra_cflags)
    
    cmd_clang = [str(CLANG_EXE)] + cflags + [str(src_path), "-o", str(out_o)]
    print(f"[*] Compiling {src_path.name} with JieLi Clang (pi32v2)...")
    res = subprocess.run(cmd_clang, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[!] Compiler error:\n{res.stderr}")
        raise RuntimeError("Clang compilation failed.")

    # 2. Gather symbol definitions into a linker script
    sym_defs = {}
    valid_sym_re = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')
    if db_path.exists():
        db = json.load(open(db_path))
        for addr_str, f in db.get("functions", {}).items():
            name = f.get("name")
            if name and not name.startswith("fn_") and not name.startswith("sub_"):
                clean_name = name.split()[0]
                if valid_sym_re.match(clean_name) and clean_name not in sym_defs:
                    sym_defs[clean_name] = int(addr_str, 16)
    
    if extra_syms:
        for k, v in extra_syms.items():
            if valid_sym_re.match(k):
                sym_defs[k] = v

    ld_syms_path = ROOT_DIR / "firmware_work" / "firmware_symbols.ld"
    with open(ld_syms_path, "w") as f_ld:
        f_ld.write("/* Auto-generated firmware symbols for SMK-37 Pro */\n")
        for s_name, s_addr in sorted(sym_defs.items()):
            f_ld.write(f"{s_name} = 0x{s_addr:08x};\n")

    # 3. Link using linker script
    ld_args = [
        str(LD_EXE),
        f"-Ttext=0x{cave_addr:08x}",
        "-T", str(ld_syms_path),
        "--oformat=binary",
        str(out_o),
        "-o", str(out_bin)
    ]

    print(f"[*] Linking at Flash 0x{cave_addr:08X} with {len(sym_defs)} symbols from {ld_syms_path.name}...")
    res_ld = subprocess.run(ld_args, capture_output=True, text=True)
    if res_ld.returncode != 0:
        print(f"[!] Linker error:\n{res_ld.stderr}")
        raise RuntimeError("pi32v2-ld linking failed.")

    # Also build ELF for disassembly inspection
    ld_elf_args = [
        str(LD_EXE),
        f"-Ttext=0x{cave_addr:08x}",
        "-T", str(ld_syms_path),
        str(out_o),
        "-o", str(out_elf)
    ]
    subprocess.run(ld_elf_args, capture_output=True)

    bin_data = out_bin.read_bytes()
    print(f"[+] Successfully compiled & linked: {len(bin_data)} bytes machine code")
    return bin_data, out_elf

def patch_and_repack(
    custom_src: Path = None,
    custom_bin_data: bytes = None,
    cave_addr: int = DEFAULT_CAVE_ADDR,
    hooks: list = None,
    byte_patches: dict = None,
    bump_version: bool = True,
    output_fwsc: Path = None
) -> Path:
    """Apply hooks and patches to app.bin and repack into valid .fwsc."""
    from tools.repack_smk import repack_firmware, APP_BIN_OFFSET, APP_BIN_SIZE

    app_bin = bytearray(DEFAULT_APP_BIN.read_bytes())
    cave_offset = cave_addr - FLASH_BASE

    # 1. Compile if source provided
    if custom_src:
        custom_bin_data, elf_path = compile_source(custom_src, cave_addr=cave_addr)

    # 2. Inject machine code into cave
    if custom_bin_data:
        code_len = len(custom_bin_data)
        if code_len > DEFAULT_CAVE_MAX_SIZE:
            raise ValueError(f"Injected code size ({code_len} B) exceeds safe cave size ({DEFAULT_CAVE_MAX_SIZE} B)")
        print(f"[*] Injecting {code_len} bytes into Flash code cave at 0x{cave_addr:08X} (offset 0x{cave_offset:06X})...")
        app_bin[cave_offset : cave_offset + code_len] = custom_bin_data

    # 3. Apply Hooks
    if hooks:
        for h in hooks:
            htype = h.get("type", "goto")  # "goto" or "call"
            target_addr = h["target_addr"]  # where the hook is placed
            dest_addr = h["dest_addr"]      # where the hook jumps to
            target_offset = target_addr - FLASH_BASE

            if htype == "goto":
                hook_bytes = encode_goto(target_addr, dest_addr)
            elif htype == "call":
                hook_bytes = encode_call(target_addr, dest_addr)
            else:
                raise ValueError(f"Unknown hook type: {htype}")

            orig_bytes = bytes(app_bin[target_offset : target_offset + len(hook_bytes)])
            app_bin[target_offset : target_offset + len(hook_bytes)] = hook_bytes
            print(f"[+] Installed {htype} hook at 0x{target_addr:08X} -> 0x{dest_addr:08X}")
            print(f"    Replaced bytes: {orig_bytes.hex()} -> {hook_bytes.hex()}")

    # 4. Apply Arbitrary Byte Patches
    if byte_patches:
        for offset_val, new_val in byte_patches.items():
            if isinstance(offset_val, str):
                off = int(offset_val, 0)
            else:
                off = int(offset_val)
            if off >= FLASH_BASE:
                off -= FLASH_BASE
            if isinstance(new_val, str):
                new_b = bytes.fromhex(new_val)
            else:
                new_b = bytes(new_val)
            orig_b = bytes(app_bin[off : off + len(new_b)])
            app_bin[off : off + len(new_b)] = new_b
            print(f"[+] Byte patch at offset 0x{off:06X}: {orig_b.hex()} -> {new_b.hex()}")

    # 5. Save patched app.bin to temporary work location
    patched_app_path = ROOT_DIR / "firmware_work" / "patched_app.bin"
    patched_app_path.write_bytes(app_bin)

    if not output_fwsc:
        output_fwsc = ROOT_DIR / "firmware_work" / "SMK-37_Pro_custom_recompiled.fwsc"

    # 6. Repack using repack_smk
    print(f"\n[*] Repacking into {output_fwsc.name}...")
    # Monkey-patch DEFAULT_APP_BIN temporarily or pass directly
    orig_app_bytes = DEFAULT_APP_BIN.read_bytes()
    try:
        DEFAULT_APP_BIN.write_bytes(app_bin)
        repack_firmware(
            stock_fwsc_path=STOCK_FWSC,
            output_fwsc_path=output_fwsc,
            apply_patches=True,
            bump_version=bump_version,
            custom_app_bin=app_bin
        )
    finally:
        DEFAULT_APP_BIN.write_bytes(orig_app_bytes)

    print(f"\n[OK] Custom firmware successfully generated: {output_fwsc}")
    return output_fwsc

if __name__ == "__main__":
    print("M-VAVE SMK-37 Pro Recompilation & Hooking Toolchain")
    print("Run tools/test_recompilation_pipeline.py for automated validation.")
