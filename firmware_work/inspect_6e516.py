with open('firmware_work/disasm/app_pi32v2_objdump.txt', 'r', encoding='utf-8', errors='replace') as f:
    capture = False
    lines = []
    for line in f:
        if ' 6e510:' in line or ' 6e516:' in line:
            capture = True
        if capture:
            lines.append(line)
            if ' 6e550:' in line:
                break
    print(''.join(lines))
