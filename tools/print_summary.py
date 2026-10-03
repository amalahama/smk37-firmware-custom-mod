import json
from collections import Counter

db = json.load(open("firmware_work/analysis/firmware_structure.json"))
print("Keys in db:", list(db.keys()))
funcs = db["functions"]
print(f"Total functions: {len(funcs)}")

first_k = next(iter(funcs))
print(f"Sample function ({first_k}):", funcs[first_k])

sources = Counter(f.get("source") for f in funcs.values())
print("Sources distribution:", sources)

subs = Counter(f.get("subsystem") for f in funcs.values())
print("Subsystems distribution:", subs)

print("\n--- Top named functions ---")
count = 0
for addr, f in funcs.items():
    if not f["name"].startswith("fn_") and not f["name"].startswith("sub_"):
        print(f"  {addr} {f['name']:<30} [{f['subsystem']:<14}] (src: {f['source']})")
        count += 1
        if count >= 30:
            break
