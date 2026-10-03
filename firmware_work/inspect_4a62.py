with open('firmware_work/disasm/app_pi32v2_objdump.txt', 'r', encoding='utf-8', errors='replace') as f:
    capture = False
    lines = []
    for line in f:
        if ' 4a40:' in line or ' 4a50:' in line:
            capture = True
        if capture:
            lines.append(line)
            if ' 4b20:' in line:
                break
    print(''.join(lines))
