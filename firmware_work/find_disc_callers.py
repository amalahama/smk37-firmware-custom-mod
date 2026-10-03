import re

with open('firmware_work/disasm/app_pi32v2_objdump.txt', 'r', encoding='utf-8', errors='replace') as f:
    for line in f:
        if ('6e700' in line or '6e6fe' in line) and ('call' in line or 'goto' in line):
            print(line.strip())
