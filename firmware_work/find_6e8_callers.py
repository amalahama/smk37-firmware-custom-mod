import re

with open('firmware_work/disasm/app_pi32v2_objdump.txt', 'r', encoding='utf-8', errors='replace') as f:
    for line in f:
        if '6e8' in line and ('call' in line or 'goto' in line or '20006e8' in line):
            print(line.strip())
