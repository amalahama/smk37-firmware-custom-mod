import json

db = json.load(open("firmware_work/analysis/firmware_structure.json"))
funcs = db["functions"]

nullsubs = [(addr, f) for addr, f in funcs.items() if "nullsub" in f["name"] or "stub" in f["name"]]
print(f"Nullsubs/stubs found: {len(nullsubs)}")
for addr, f in nullsubs[:10]:
    print(f"  {addr}  {f['name']:<25} size={f['size']:<4} callers={len(f['callers'])}")

print("\n--- Zero / Padding runs in app.bin ---")
data = open("firmware_work/v16_unpacked/files/app.bin", "rb").read()
# Find runs of 0x00 or 0xFF of length >= 32
runs = []
cur_byte = None
start = 0
for i, b in enumerate(data):
    if b in (0x00, 0xFF):
        if cur_byte == b:
            pass
        else:
            if cur_byte is not None and (i - start) >= 32:
                runs.append((start, i - start, cur_byte))
            cur_byte = b
            start = i
    else:
        if cur_byte is not None and (i - start) >= 32:
            runs.append((start, i - start, cur_byte))
        cur_byte = None

print(f"Found {len(runs)} padding runs >= 32 bytes:")
for off, sz, b in sorted(runs, key=lambda x: -x[1])[:15]:
    flash_addr = 0x02000000 + off
    print(f"  Offset 0x{off:06X} (Flash 0x{flash_addr:08X}): {sz:4d} bytes of 0x{b:02X}")
