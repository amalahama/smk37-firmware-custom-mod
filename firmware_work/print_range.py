with open('firmware_work/disasm/app_pi32v2_objdump.txt', 'r', encoding='utf-8', errors='replace') as f:
    for line in f:
        if any(f' {h:x}:' in line for h in range(0x740, 0x785, 2)):
            print(line.rstrip())
