import re

with open('firmware_work/disasm/app_pi32v2_objdump.txt', 'r', encoding='utf-8', errors='replace') as f:
    for line_num, line in enumerate(f):
        # Look for hex constants like 20583 or 204ab
        if any(term in line.lower() for term in ['20583', '204ab', '20584', '20587']):
            print(f"{line_num}: {line.strip()}")
