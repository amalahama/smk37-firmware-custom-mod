import subprocess
for b in [bytes.fromhex('bd44'), bytes.fromhex('bd45'), bytes.fromhex('bd40'), bytes.fromhex('b844')]:
    with open('firmware_work/_tmp_insn.bin', 'wb') as f:
        f.write(b)
    with open('firmware_work/_tmp_insn.S', 'w') as f:
        f.write('.section .fw, "ax"\n.incbin "firmware_work/_tmp_insn.bin"\n')
    subprocess.run(['toolchain/C$/JL/pi32/bin/clang.exe', '-c', '-target', 'pi32v2', 'firmware_work/_tmp_insn.S', '-o', 'firmware_work/_tmp_insn.o'])
    out = subprocess.check_output(['toolchain/C$/JL/pi32/bin/llvm-objdump.exe', '-d', 'firmware_work/_tmp_insn.o']).decode()
    for l in out.splitlines():
        if '0:' in l:
            print(b.hex(), '->', l.strip())
