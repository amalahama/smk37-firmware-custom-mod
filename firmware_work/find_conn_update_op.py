import re

with open('firmware_work/disasm/app_pi32v2_objdump.txt', 'r', encoding='utf-8', errors='replace') as f:
    for line in f:
        if '2013' in line and ('13 20' in line or '20 13' in line or '8211' in line):
            print(line.strip())
