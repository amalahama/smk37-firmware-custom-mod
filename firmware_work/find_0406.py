with open('firmware_work/disasm/app_pi32v2_objdump.txt', 'r', encoding='utf-8', errors='replace') as f:
    for line in f:
        if '1030' in line or '0406' in line:
            if any(r in line for r in ['r2 = ', 'r1 = ', 'r0 = ']):
                print(line.strip())
