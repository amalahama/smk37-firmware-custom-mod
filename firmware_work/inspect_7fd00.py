with open('firmware_work/disasm/app_pi32v2_objdump.txt', 'r', encoding='utf-8', errors='replace') as f:
    lines = []
    capture = False
    for line in f:
        if ' 7fd00:' in line or ' 7fcfe:' in line:
            capture = True
        if capture:
            lines.append(line)
            if ' 7fd52:' in line:
                break
    print(''.join(lines))
