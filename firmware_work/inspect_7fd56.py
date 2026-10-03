with open('firmware_work/disasm/app_pi32v2_objdump.txt', 'r', encoding='utf-8', errors='replace') as f:
    lines = []
    capture = False
    for line in f:
        if ' 7fd40:' in line or ' 7fd50:' in line:
            capture = True
        if capture:
            lines.append(line)
            if len(lines) > 40:
                break
    print(''.join(lines))
