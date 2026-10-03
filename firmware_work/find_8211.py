with open('firmware_work/disasm/app_pi32v2_objdump.txt', 'r', encoding='utf-8', errors='replace') as f:
    for line in f:
        if '8211' in line or '2013' in line:
            if 'r2 = ' in line or 'r1 = ' in line or 'r0 = ' in line:
                print(line.strip())
