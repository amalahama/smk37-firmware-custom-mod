with open('firmware_work/disasm/strings_raw.txt') as f:
    lines = [line.strip().split('\t') for line in f if '\t' in line]

real_strings = [(int(off, 16), val) for off, val in lines if int(off, 16) >= 0x50000 and len(val) >= 4]
print(f'Meaningful strings (offset >= 0x50000): {len(real_strings)}')
for off, val in real_strings[:25]:
    target_addr = 0x02000000 + off
    print(f'  Offset 0x{off:06X} (Flash 0x{target_addr:08X}): "{val}"')

print("\n--- Searching for code references to these strings ---")
found_count = 0
for off, val in real_strings:
    target_addr = 0x02000000 + off
    hex_patterns = [f"{target_addr:x}", f"{target_addr:X}"]
    with open('firmware_work/disasm/app_pi32v2_objdump.txt') as f:
        for i, line in enumerate(f):
            if any(pat in line for pat in hex_patterns):
                print(f'  [DIRECT] "{val}" (0x{target_addr:08X}) at line {i}: {line.strip()}')
                found_count += 1
                break
    if found_count >= 15:
        break
