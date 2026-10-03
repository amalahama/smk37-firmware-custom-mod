with open('firmware_work/disasm/app_pi32v2_objdump.txt', 'r', encoding='utf-8', errors='replace') as f:
    for line_num, line in enumerate(f):
        if '5839' in line or '583a' in line or '5838' in line:
            print(f"{line_num}: {line.strip()}")
