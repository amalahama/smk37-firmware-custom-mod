#!/usr/bin/env python3
"""tools/analyze_firmware.py — Comprehensive Decompilation, Function Catalog & Subsystem Classifier
for M-VAVE SMK-37 Pro Firmware (JieLi AC791N / pi32v2)
"""
import os
import re
import sys
import json
import struct
from collections import defaultdict

BASE_ADDR = 0x02000000
APP_BIN = r"firmware_work/v16_unpacked/files/app.bin"
OBJDUMP_TXT = r"firmware_work/disasm/app_pi32v2_objdump.txt"
LIBDIS_DIR = r"FM-1-RE/analysis/libdis"
OUT_DIR = r"firmware_work/analysis"

def extract_strings(data, base_addr):
    """Extract printable strings with their file offsets and flash addresses."""
    strings = {}
    srx = re.compile(rb'[\x20-\x7e]{3,}')
    for m in srx.finditer(data):
        strings[base_addr + m.start()] = m.group().decode('ascii', 'replace')
    return strings

def find_pointer_tables(data, base_addr, strings_set):
    """Identify pointer tables in rodata pointing to strings."""
    ptr_sites = []
    for off in range(0, len(data) - 3, 4):
        w = struct.unpack_from("<I", data, off)[0]
        if w in strings_set:
            ptr_sites.append((base_addr + off, w))
    
    # Group nearby pointer sites into table regions
    regions = []
    cur = []
    for loc, tgt in ptr_sites:
        if cur and loc - cur[-1][0] > 64:
            regions.append(cur)
            cur = []
        cur.append((loc, tgt))
    if cur:
        regions.append(cur)
    return ptr_sites, regions

def load_library_signatures(libdis_dir, min_len=6):
    """Load canonical instruction signatures from toolchain libraries."""
    if not os.path.exists(libdis_dir):
        print(f"[!] Warning: {libdis_dir} not found. Skipping library matching.")
        return {}

    line_re = re.compile(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2} )+)\s*\t(.*)$')
    func_re = re.compile(r'^([A-Za-z_][A-Za-z0-9_$]*):\s*$')
    ann_re  = re.compile(r'<[^>]*>')
    num_re  = re.compile(r'(0x[0-9a-fA-F]+|-?\d+)')

    def canon(text):
        t = ann_re.sub('', text)
        t = num_re.sub('#', t)
        return re.sub(r'\s+', ' ', t).strip()

    sig2names = defaultdict(set)
    for fn in os.listdir(libdis_dir):
        if not fn.endswith('.txt'):
            continue
        fp = os.path.join(libdis_dir, fn)
        name, cur = None, []
        for ln in open(fp, errors='replace'):
            fm = func_re.match(ln)
            if fm:
                if name and cur and len(cur) >= min_len:
                    sig2names["\n".join(cur)].add(name)
                name, cur = fm.group(1), []
                continue
            m = line_re.match(ln)
            if m and name is not None:
                cur.append(canon(m.group(3)))
        if name and cur and len(cur) >= min_len:
            sig2names["\n".join(cur)].add(name)
    return sig2names

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("=" * 65)
    print("  SMK-37 Pro Firmware Decompilation & Function Analysis")
    print("=" * 65)

    if not os.path.exists(APP_BIN) or not os.path.exists(OBJDUMP_TXT):
        print("[ERROR] Required input files missing. Run tools/disasm_firmware.py first.")
        return 1

    app_data = open(APP_BIN, "rb").read()
    code_size = len(app_data)
    code_end = BASE_ADDR + code_size
    print(f"[*] App binary size: {code_size} bytes (0x{code_size:X})")
    print(f"[*] Address space:   0x{BASE_ADDR:08X} .. 0x{code_end:08X}")

    # 1. Strings
    print("[*] Extracting string literals and symbols...")
    strings = extract_strings(app_data, BASE_ADDR)
    strings_set = set(strings.keys())
    print(f"    -> Found {len(strings)} printable strings")

    # 2. Pointer tables
    print("[*] Detecting indirect pointer tables...")
    ptr_sites, ptr_regions = find_pointer_tables(app_data, BASE_ADDR, strings_set)
    print(f"    -> Found {len(ptr_sites)} string pointers grouped into {len(ptr_regions)} table regions")

    # 3. Parse disassembly instructions
    print("[*] Parsing disassembly instructions from objdump...")
    line_re = re.compile(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2} )+)\s*\t(.*)$')
    ann_re  = re.compile(r'<_fw\+0x([0-9a-fA-F]+)')
    branch_re = re.compile(r'\b(call|goto|gotoss|jmp)\b')

    insns = []
    for ln in open(OBJDUMP_TXT, errors='replace'):
        m = line_re.match(ln)
        if not m:
            continue
        off = int(m.group(1), 16)
        nbytes = len(m.group(2).split())
        addr = BASE_ADDR + off
        text = m.group(3).rstrip()
        mnem = text.split(None, 1)[0] if text else ''
        refs = []
        for hx in ann_re.findall(text):
            v = int(hx, 16)
            if branch_re.search(text):
                tgt = (BASE_ADDR + v) & 0xffffffff
            else:
                tgt = v & 0xffffffff
            refs.append(tgt)
        insns.append((addr, nbytes, mnem, text, refs))

    insns.sort()
    print(f"    -> Parsed {len(insns)} machine instructions")

    # 4. Discover function entry points
    print("[*] Discovering function boundaries from call graph & vectors...")
    callcnt = defaultdict(int)
    for a, nb, mn, tx, refs in insns:
        if mn == 'call':
            for t in refs:
                callcnt[t] += 1

    entries = set(t for t in callcnt if BASE_ADDR <= t < code_end)
    entries.add(BASE_ADDR + 0) # CRT0 entry
    entries = sorted(entries)
    print(f"    -> Identified {len(entries)} function entries in Flash")

    # Build function records
    functions = {}
    for i, e in enumerate(entries):
        nxt = entries[i + 1] if i + 1 < len(entries) else code_end
        functions[e] = {
            "addr": e, "end": nxt, "size": nxt - e,
            "callers": [], "callees": [],
            "str_refs": [], "ram_refs": [], "code_ptr_refs": [],
            "ninsns": 0, "name": f"fn_{e:08X}", "subsystem": "Unknown",
            "insn_texts": []
        }

    def get_owner(addr):
        import bisect
        i = bisect.bisect_right(entries, addr) - 1
        if i >= 0:
            e = entries[i]
            if e <= addr < functions[e]["end"]:
                return e
        return None

    # Walk instructions and attribute references
    ann_strip_re = re.compile(r'<[^>]*>')
    num_strip_re = re.compile(r'(0x[0-9a-fA-F]+|-?\d+)')
    def canon_text(tx):
        t = ann_strip_re.sub('', tx)
        t = num_strip_re.sub('#', t)
        return re.sub(r'\s+', ' ', t).strip()

    for a, nb, mn, tx, refs in insns:
        o = get_owner(a)
        if o is None:
            continue
        f = functions[o]
        f["ninsns"] += 1
        f["insn_texts"].append(canon_text(tx))

        for t in refs:
            if mn == 'call':
                if BASE_ADDR <= t < code_end:
                    f["callees"].append(t)
                    if o != t:
                        functions[t]["callers"].append(a)
            elif not branch_re.search(tx):
                if BASE_ADDR <= t < code_end:
                    if t in strings:
                        f["str_refs"].append(t)
                    else:
                        f["code_ptr_refs"].append(t)
                elif 0x01c00000 <= t < 0x01c80000:
                    f["ram_refs"].append(t)

    # Attach table strings to functions referencing nearby table regions
    for e, f in functions.items():
        for r_addr in f["code_ptr_refs"]:
            for r in ptr_regions:
                if r[0][0] - 8 <= r_addr <= r[-1][0] + 8:
                    for loc, tgt in r:
                        if tgt in strings and tgt not in f["str_refs"]:
                            f["str_refs"].append(tgt)

    # 5. Toolchain library signature matching
    print("[*] Matching against toolchain SDK library signatures...")
    lib_sigs = load_library_signatures(LIBDIS_DIR)
    matched_lib_count = 0
    for e, f in functions.items():
        sig = "\n".join(f["insn_texts"])
        if sig in lib_sigs:
            names = list(lib_sigs[sig])
            f["name"] = names[0]
            f["subsystem"] = "SDK_Library"
            matched_lib_count += 1
    print(f"    -> Matched {matched_lib_count} standard SDK functions")

    # 6. Classify subsystems based on strings & signatures
    print("[*] Classifying firmware subsystems...")
    subsystems_def = [
        ("BLE_Stack", [r"\bble\b", r"\bgatt\b", r"\badv\b", r"\bbluetooth\b", r"\bbond\b", r"\ble\b", r"03b80e5a"]),
        ("MIDI_Engine", [r"\bmidi\b", r"\bchannel\b", r"\bvel\b", r"\bvelocity\b", r"\bnote\b", r"\bcc\b", r"\bsysex\b"]),
        ("FM_Synth_DX7", [r"\bdx7\b", r"\bfm\b", r"\boperator\b", r"\bpatch\b", r"\bvoice\b", r"\bosc\b", r"\bsin\b", r"\bmsfa\b", r"\bdexed\b"]),
        ("Audio_DAC_I2S", [r"\baudio\b", r"\bi2s\b", r"\bdac\b", r"\bvolume\b", r"\bsample\b", r"\brate\b", r"\bcs4344\b"]),
        ("Sequencer_Arp", [r"\bseq\b", r"\bsequence\b", r"\barp\b", r"\barpeggiator\b", r"\btempo\b", r"\bbpm\b", r"\brepeat\b"]),
        ("Hardware_UI", [r"\bkey\b", r"\bkeys\b", r"\bpad\b", r"\bled\b", r"\bdisplay\b", r"\bbutton\b", r"\bwheel\b", r"\btouch\b", r"\bencoder\b", r"\bstrip\b"]),
        ("USB_Controller", [r"\busb\b", r"\buac\b", r"\bendpoint\b", r"\bdescriptor\b", r"\bhid\b"]),
        ("Storage_JLFS", [r"\bjlfs\b", r"\bflash\b", r"\bspi\b", r"\bconfig\b", r"\bsdram\b", r"\bsector\b", r"\bcfg\b"]),
        ("System_Boot", [r"\bboot\b", r"\breset\b", r"\bclock\b", r"\birq\b", r"\binterrupt\b", r"\bwatchdog\b", r"\btimer\b"])
    ]

    subsystem_counts = defaultdict(int)

    for e, f in functions.items():
        if f["name"] == f"fn_{e:08X}": # Not already identified by lib match
            # Gather all associated strings
            f_strings = [strings[s] for s in f["str_refs"] if s in strings]
            f_text = " ".join(f_strings).lower()
            
            # CRT0 entry
            if e == BASE_ADDR:
                f["name"] = "crt0_entry"
                f["subsystem"] = "System_Boot"
                continue

            matched = False
            for sub_name, patterns in subsystems_def:
                for pat in patterns:
                    if re.search(pat, f_text, re.IGNORECASE):
                        f["subsystem"] = sub_name
                        # If a prominent string exists, derive a readable name
                        for s in f_strings:
                            clean_s = re.sub(r'[^a-zA-Z0-9_]', '_', s).strip('_')
                            if 3 <= len(clean_s) <= 24 and not clean_s.isdigit():
                                f["name"] = f"{sub_name[:4].lower()}_{clean_s}_{e:06X}"
                                break
                        matched = True
                        break
                if matched:
                    break
        subsystem_counts[f["subsystem"]] += 1

    print("\n  Subsystem Breakdown:")
    for sub, count in sorted(subsystem_counts.items(), key=lambda x: -x[1]):
        print(f"    - {sub:<16}: {count:4d} functions")

    # 7. Write outputs
    csv_path = os.path.join(OUT_DIR, "functions_catalog.csv")
    print(f"\n[*] Writing function catalog -> {csv_path}...")
    with open(csv_path, "w", encoding="utf-8") as f_csv:
        f_csv.write("address,size,name,subsystem,n_insns,n_callers,n_callees,referenced_strings\n")
        for e in entries:
            f = functions[e]
            s_list = "; ".join(strings[s] for s in f["str_refs"] if s in strings)[:100].replace(",", " ")
            f_csv.write(f"0x{e:08X},{f['size']},{f['name']},{f['subsystem']},{f['ninsns']},{len(f['callers'])},{len(f['callees'])},\"{s_list}\"\n")

    json_path = os.path.join(OUT_DIR, "firmware_structure.json")
    print(f"[*] Writing detailed structure -> {json_path}...")
    out_db = {
        "base_address": f"0x{BASE_ADDR:08X}",
        "code_end": f"0x{code_end:08X}",
        "code_size": code_size,
        "total_functions": len(functions),
        "subsystem_counts": dict(subsystem_counts),
        "functions": {
            f"0x{e:08X}": {
                "name": f["name"],
                "subsystem": f["subsystem"],
                "size": f["size"],
                "n_insns": f["ninsns"],
                "callers": [f"0x{c:08X}" for c in f["callers"]],
                "callees": [f"0x{c:08X}" for c in f["callees"]],
                "strings": [strings[s] for s in f["str_refs"] if s in strings]
            }
            for e in entries
        }
    }
    with open(json_path, "w", encoding="utf-8") as f_json:
        json.dump(out_db, f_json, indent=2)

    print("\n[OK] Analysis completed successfully!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
