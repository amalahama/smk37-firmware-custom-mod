import subprocess

code = bytes.fromhex('03 e1 89 66 bf 40 40 21 b8 41 40 26 b8 42 41 31 b9 43 39 85 c2 ff 19 7e 05 02 05 f1 95 26 bd 44 10 8f 57 07 97 07 41 e0 9e 06 d8 ee 61 01 18 81 79 3f d8 ee 61 10 38 97 10 84 21 07 81 07 40 23 41 22 42 3c 80 ff 64 d7 07 00')
with open('firmware_work/snippet.bin', 'wb') as f:
    f.write(code)

with open('firmware_work/snippet.S', 'w') as f:
    f.write('.section .text\n.incbin "firmware_work/snippet.bin"\n')

subprocess.run([r'toolchain\C$\JL\pi32\bin\clang.exe', '-c', '-target', 'pi32v2', 'firmware_work/snippet.S', '-o', 'firmware_work/snippet.o'])
res = subprocess.run([r'toolchain\C$\JL\pi32\bin\llvm-objdump.exe', '-d', 'firmware_work/snippet.o'], capture_output=True, text=True)
print(res.stdout)
