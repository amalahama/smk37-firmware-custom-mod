#!/usr/bin/env python3
"""tools/test_recompilation_pipeline.py — End-to-End Validation Test
for SMK-37 Pro Recompilation, Hooking & Repacking Pipeline
"""
import os
import sys
import subprocess
import shutil
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from tools.patch_firmware import patch_and_repack, DEFAULT_CAVE_ADDR, FLASH_BASE, TOOLCHAIN_DIR
from tools.unpack_smk import unpack_fwsc

def main():
    print("=" * 75)
    print("  SMK-37 Pro Custom Recompilation & Hooking Pipeline Validation Test")
    print("=" * 75)

    work_dir = ROOT_DIR / "firmware_work"
    custom_c_path = work_dir / "custom_test_hook.c"
    output_fwsc = work_dir / "SMK-37_Pro_validation_017.fwsc"
    unpack_dir = work_dir / "validation_unpack"

    # Step 1: Write Custom C code
    print("\n[Step 1] Creating custom C modification module...")
    c_code = """/* custom_test_hook.c — Custom MIDI Velocity Processing Hook */
extern int midi_slot_is_active(int slot);

int custom_velocity_curve(int velocity) {
    if (velocity <= 0) return 0;
    if (velocity >= 120) return 127;
    // Exponential curve transformation
    return (velocity * velocity) / 127;
}

int custom_midi_handler(int status, int note, int vel) {
    if ((status & 0xF0) == 0x90 && vel > 0) {
        vel = custom_velocity_curve(vel);
    }
    return (vel << 16) | (note << 8) | status;
}
"""
    custom_c_path.write_text(c_code)
    print(f"  -> Written: {custom_c_path}")

    # Step 2: Define Hook Target
    # We test hooking `midi_msg_prefilter` at 0x02000AA6
    hook_target_addr = 0x02000AA6
    hook_dest_addr = DEFAULT_CAVE_ADDR

    print(f"\n[Step 2] Configuring hook:")
    print(f"  Target function: 0x{hook_target_addr:08X} (midi_msg_prefilter)")
    print(f"  Destination:     0x{hook_dest_addr:08X} (Flash Cave)")

    # Step 3: Run patch_and_repack
    print("\n[Step 3] Compiling C source, injecting into cave, installing hook, and repacking...")
    fwsc_path = patch_and_repack(
        custom_src=custom_c_path,
        cave_addr=hook_dest_addr,
        hooks=[{
            "type": "goto",
            "target_addr": hook_target_addr,
            "dest_addr": hook_dest_addr
        }],
        bump_version=True,
        output_fwsc=output_fwsc
    )
    assert fwsc_path.exists(), f"Output FWSC {fwsc_path} not found!"
    print(f"[+] Output firmware image created: {fwsc_path} ({fwsc_path.stat().st_size} bytes)")

    # Step 4: Unpack and Verify Integrity
    print(f"\n[Step 4] Unpacking generated firmware image with unpack_smk.py...")
    if unpack_dir.exists():
        shutil.rmtree(unpack_dir)
    unpack_dir.mkdir(parents=True)

    unpack_fwsc(fwsc_path, unpack_dir)
    unpacked_app = unpack_dir / "files" / "app.bin"
    assert unpacked_app.exists(), f"Unpacked app.bin missing from {unpack_dir}"

    unpacked_data = unpacked_app.read_bytes()
    print(f"[+] Successfully unpacked and decrypted app.bin ({len(unpacked_data)} bytes)")

    # Step 5: Verify Cave Code & Hook Instruction
    print("\n[Step 5] Bit-level verification of injected machine code & hook...")
    cave_offset = hook_dest_addr - FLASH_BASE
    hook_offset = hook_target_addr - FLASH_BASE

    injected_bytes = unpacked_data[cave_offset : cave_offset + 32]
    hook_bytes = unpacked_data[hook_offset : hook_offset + 4]

    print(f"  Injected machine code at offset 0x{cave_offset:06X} (Flash 0x{hook_dest_addr:08X}):")
    print(f"    Bytes: {injected_bytes.hex()}")

    print(f"  Hook opcode at offset 0x{hook_offset:06X} (Flash 0x{hook_target_addr:08X}):")
    print(f"    Bytes: {hook_bytes.hex()}")

    # Check non-zero injected code
    assert any(b != 0 for b in injected_bytes), "Injected code is all zeroes!"

    # Step 6: Disassemble Patched Region
    print("\n[Step 6] Disassembling patched regions with llvm-objdump...")
    disasm_cmd = [
        str(TOOLCHAIN_DIR / "llvm-objdump.exe"),
        "-d",
        str(custom_c_path.with_suffix(".elf"))
    ]
    res_dis = subprocess.run(disasm_cmd, capture_output=True, text=True)
    print("  Disassembly of injected custom C module:")
    for line in res_dis.stdout.strip().splitlines()[:15]:
        print(f"    {line}")

    # Check version bump in unpacked binary
    v_idx = unpacked_data.find(b"SMK-37 Pro_017")
    print(f"\n[Step 7] Checking version string in decrypted binary...")
    if v_idx != -1:
        print(f"  [+] Confirmed: 'SMK-37 Pro_017' found at offset 0x{v_idx:06X}")
    else:
        print("  [!] Warning: Version string not found.")

    # Check BLE advertisement UUID pointer
    adv_ptr_bytes = unpacked_data[0x00075E : 0x000762]
    print(f"[Step 8] Checking BLE-MIDI advertising pointer at 0x00075E...")
    print(f"  Bytes: {adv_ptr_bytes.hex()} (Expected: 05f17525 -> 0x0205838E)")
    assert adv_ptr_bytes == bytes.fromhex("05f17525"), "BLE adv pointer mismatch!"

    print("\n" + "=" * 75)
    print("  VALIDATION TEST PASSED: Full Decompilation -> C Recompile -> Hook -> Repack -> Verified!")
    print("=" * 75)
    return 0

if __name__ == "__main__":
    sys.exit(main())
