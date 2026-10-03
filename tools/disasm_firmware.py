#!/usr/bin/env python3
"""tools/disasm_firmware.py — Disassemble SMK-37 Pro app.bin using native JieLi pi32v2 toolchain
"""
import os
import sys
import time
import subprocess

APP_BIN = r"firmware_work/v16_unpacked/files/app.bin"
WORK_DIR = r"firmware_work/disasm"
WRAP_S = os.path.join(WORK_DIR, "app_full.S")
WRAP_O = os.path.join(WORK_DIR, "app_full.o")
DUMP_TXT = os.path.join(WORK_DIR, "app_pi32v2_objdump.txt")

CLANG_EXE = r"toolchain/C$/JL/pi32/bin/clang.exe"
OBJDUMP_EXE = r"toolchain/C$/JL/pi32/bin/llvm-objdump.exe"

def main():
    os.makedirs(WORK_DIR, exist_ok=True)
    if not os.path.exists(APP_BIN):
        print(f"[ERROR] {APP_BIN} not found!")
        return 1

    print(f"[*] App binary: {APP_BIN} ({os.path.getsize(APP_BIN)} bytes)")
    
    # 1. Create assembly wrapper
    app_bin_abs = os.path.abspath(APP_BIN).replace("\\", "/")
    print(f"[*] Writing assembly wrapper {WRAP_S}...")
    with open(WRAP_S, "w", encoding="utf-8") as f:
        f.write(f'.section .fw, "ax", @progbits\n.globl _fw\n_fw:\n.incbin "{app_bin_abs}"\n')

    # 2. Compile to ELF object using JieLi clang
    print("[*] Assembling ELF object using JieLi clang (target=pi32v2)...")
    t0 = time.time()
    res = subprocess.run([CLANG_EXE, "-c", "-target", "pi32v2", WRAP_S, "-o", WRAP_O])
    if res.returncode != 0:
        print("[ERROR] Clang assembly failed!")
        return 1
    print(f"[OK] Object file generated ({os.path.getsize(WRAP_O)} bytes in {time.time()-t0:.2f}s)")

    # 3. Disassemble using llvm-objdump
    print("[*] Running llvm-objdump to generate complete disassembly...")
    t1 = time.time()
    with open(DUMP_TXT, "w", encoding="utf-8", errors="replace") as out_f:
        res = subprocess.run([OBJDUMP_EXE, "-d", WRAP_O], stdout=out_f)
    if res.returncode != 0:
        print("[ERROR] llvm-objdump failed!")
        return 1
    print(f"[OK] Disassembly complete: {DUMP_TXT} ({os.path.getsize(DUMP_TXT)} bytes in {time.time()-t1:.2f}s)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
