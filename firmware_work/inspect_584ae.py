with open('firmware_work/v16_unpacked/files/app.bin', 'rb') as f:
    data = f.read()

sub = data[0x058480:0x058520]
for off in range(0, len(sub), 16):
    chunk = sub[off:off+16]
    hex_str = ' '.join(f'{b:02x}' for b in chunk)
    asc_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
    print(f'0x{0x058480 + off:06X}:  {hex_str:<48}  {asc_str}')
