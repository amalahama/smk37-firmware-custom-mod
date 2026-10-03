import re

with open('firmware_work/disasm/app_pi32v2_objdump.txt', 'r', encoding='utf-8', errors='replace') as f:
    for line in f:
        m = re.match(r'^\s+([0-9a-f]+):', line)
        if m:
            addr = int(m.group(1), 16)
            if 0x89480 <= addr <= 0x89520:
                print(line.rstrip())
