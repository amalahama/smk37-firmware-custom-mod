with open('firmware_work/disasm/app_pi32v2_objdump.txt', 'r', encoding='utf-8', errors='replace') as f:
    capture = False
    lines = []
    for line in f:
        if ' 7def2:' in line:
            capture = True
        if capture:
            lines.append(line)
            if len(lines) > 30:
                break
    print(''.join(lines))
