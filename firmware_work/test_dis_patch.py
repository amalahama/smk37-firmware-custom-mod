import subprocess

for hex_bytes in ["05f19526", "05f17525"]:
    b = bytes.fromhex(hex_bytes)
    with open('firmware_work/_tmp_insn.bin', 'wb') as f:
        f.write(b)
    with open('firmware_work/_tmp_insn.S', 'w') as f:
        f.write('.section .fw, "ax"\n.incbin "firmware_work/_tmp_insn.bin"\n')
    subprocess.run(['toolchain/C$/JL/pi32/bin/clang.exe', '-c', '-target', 'pi32v2', 'firmware_work/_tmp_insn.S', '-o', 'firmware_work/_tmp_insn.o'])
    out = subprocess.check_output(['toolchain/C$/JL/pi32/bin/llvm-objdump.exe', '-d', 'firmware_work/_tmp_insn.o']).decode()
    print(hex_bytes, ":")
    for l in out.splitlines():
        if '0:' in l:
            print(" ", l.strip())
