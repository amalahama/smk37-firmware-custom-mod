import subprocess

with open('firmware_work/v16_unpacked/files/app.bin', 'rb') as f:
    hdr = f.read(128)

with open('firmware_work/app_head.bin', 'wb') as f:
    f.write(hdr)

with open('firmware_work/app_head.S', 'w') as f:
    f.write('.section .fw, "ax", @progbits\n_fw:\n.incbin "firmware_work/app_head.bin"\n')

subprocess.run([r'toolchain\C$\JL\pi32\bin\clang.exe', '-c', '-target', 'pi32v2', 'firmware_work/app_head.S', '-o', 'firmware_work/app_head.o'])
res = subprocess.run([r'toolchain\C$\JL\pi32\bin\llvm-objdump.exe', '-d', 'firmware_work/app_head.o'], capture_output=True, text=True)
print(res.stdout)
