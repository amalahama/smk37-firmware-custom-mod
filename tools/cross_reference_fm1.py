#!/usr/bin/env python3
"""tools/cross_reference_fm1.py
Cross-reference SMK-37 Pro disassembled firmware against FM-1 reverse engineering
database (2,062 functions) and toolchain library signatures.
"""
import os
import re
import sys
import json
from collections import defaultdict, Counter

BASE_ADDR = 0x02000000
APP_BIN = r"firmware_work/v16_unpacked/files/app.bin"
OBJDUMP_TXT = r"firmware_work/disasm/app_pi32v2_objdump.txt"
FM1_DB = r"FM-1-RE/analysis/db.json"
FM1_CLASSIFIED = r"FM-1-RE/analysis/master_classified.json"
LIBDIS_DIR = r"FM-1-RE/analysis/libdis"
OUT_DIR = r"firmware_work/analysis"

ann_re  = re.compile(r'<[^>]*>')
num_re  = re.compile(r'(0x[0-9a-fA-F]+|-?\d+)')
line_re = re.compile(r'^\s*([0-9a-f]+):\s+((?:[0-9a-f]{2} )+)\s*\t(.*)$')
ann_fw_re = re.compile(r'<_fw\+0x([0-9a-fA-F]+)')
branch_re = re.compile(r'\b(call|goto|gotoss|jmp)\b')

def canon(text):
    t = ann_re.sub('', text)
    t = num_re.sub('#', t)
    return re.sub(r'\s+', ' ', t).strip()

def load_lib_signatures(libdis_dir, min_len=4):
    if not os.path.exists(libdis_dir):
        return {}
    func_re = re.compile(r'^([A-Za-z_][A-Za-z0-9_$]*):\s*$')
    sig2names = defaultdict(set)
    for fn in os.listdir(libdis_dir):
        if not fn.endswith('.txt'): continue
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
    print("=" * 70)
    print(" SMK-37 Pro <-> FM-1 RE & Toolchain Deep Cross-Reference")
    print("=" * 70)

    # 1. Load FM-1 database
    print("[*] Loading FM-1 function database...")
    fm1_db = json.load(open(FM1_DB))
    fm1_classified = json.load(open(FM1_CLASSIFIED))
    
    fm1_canon_map = {}
    for a_str, fn in fm1_db['functions'].items():
        c = fn.get('canon')
        if c and c.count('\n') + 1 >= 3:
            addr_hex = f"0x{fn['addr']:08x}"
            meta = fm1_classified.get(addr_hex, {})
            sub = meta.get('subsystem') or fn.get('subsystem') or 'UNKNOWN'
            name = fn.get('name')
            purpose = meta.get('purpose') or fn.get('purpose') or ''
            fm1_canon_map[c] = {
                'name': name,
                'subsystem': sub,
                'purpose': purpose,
                'fm1_addr': addr_hex
            }
    print(f"    -> Indexed {len(fm1_canon_map)} unique FM-1 function signatures")

    # 2. Load toolchain signatures
    print("[*] Loading toolchain SDK signatures...")
    lib_sigs = load_lib_signatures(LIBDIS_DIR)
    print(f"    -> Indexed {len(lib_sigs)} toolchain SDK signatures")

    # 3. Parse SMK-37 disassembly
    print("[*] Parsing SMK-37 Pro instructions...")
    insns = []
    app_data = open(APP_BIN, "rb").read()
    code_size = len(app_data)
    code_end = BASE_ADDR + code_size

    for ln in open(OBJDUMP_TXT, errors='replace'):
        m = line_re.match(ln)
        if not m: continue
        off = int(m.group(1), 16)
        nbytes = len(m.group(2).split())
        addr = BASE_ADDR + off
        text = m.group(3).rstrip()
        mnem = text.split(None, 1)[0] if text else ''
        refs = []
        for hx in ann_fw_re.findall(text):
            v = int(hx, 16)
            if branch_re.search(text):
                tgt = (BASE_ADDR + v) & 0xffffffff
            else:
                tgt = v & 0xffffffff
            refs.append(tgt)
        insns.append((addr, nbytes, mnem, text, refs, canon(text)))

    insns.sort()
    print(f"    -> Parsed {len(insns)} machine instructions (End: 0x{code_end:08X})")

    # 4. Extract C strings
    print("[*] Extracting string literals from SMK-37 binary...")
    strings = {}
    for m in re.finditer(rb'[\x20-\x7e]{4,}\x00', app_data):
        strings[BASE_ADDR + m.start()] = m.group()[:-1].decode('ascii', 'replace')
    print(f"    -> Found {len(strings)} null-terminated ASCII strings")

    # 5. Function Entry Detection
    callcnt = Counter()
    for a, nb, mn, tx, refs, cn in insns:
        if mn == 'call':
            for t in refs:
                if BASE_ADDR <= t < code_end:
                    callcnt[t] += 1
    entries = sorted(set(callcnt.keys()) | {BASE_ADDR, BASE_ADDR + 0xA0})
    print(f"    -> Detected {len(entries)} function entries in Flash")

    # Build function records
    functions = {}
    for i, e in enumerate(entries):
        nxt = entries[i + 1] if i + 1 < len(entries) else code_end
        functions[e] = {
            "addr": e,
            "end": nxt,
            "size": nxt - e,
            "callers": [],
            "callees": [],
            "str_refs": [],
            "ram_refs": [],
            "code_ptr_refs": [],
            "canons": [],
            "ninsns": 0,
            "name": f"fn_{e:08X}",
            "subsystem": "UNCLASSIFIED",
            "purpose": "",
            "match_source": "none",
            "confidence": "none"
        }

    import bisect
    def get_owner(addr):
        i = bisect.bisect_right(entries, addr) - 1
        if i >= 0:
            e = entries[i]
            if e <= addr < functions[e]["end"]:
                return e
        return None

    # Attribute instructions and references
    for a, nb, mn, tx, refs, cn in insns:
        o = get_owner(a)
        if o is None: continue
        f = functions[o]
        f["ninsns"] += 1
        f["canons"].append(cn)

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

    # 6. Pass 1: Toolchain Library Matching
    print("[*] Pass 1: Matching against Toolchain SDK Libraries...")
    lib_matches = 0
    for e, f in functions.items():
        sig = "\n".join(f["canons"])
        if sig in lib_sigs:
            names = sorted(lib_sigs[sig])
            f["name"] = names[0]
            f["subsystem"] = "MATHLIB" if "libm" in names[0] else "MEMLIB"
            f["purpose"] = f"Toolchain SDK: {names[0]}"
            f["match_source"] = "toolchain_lib"
            f["confidence"] = "high"
            lib_matches += 1
    print(f"    -> Matched {lib_matches} functions to Toolchain SDK")

    # 7. Pass 2: FM-1 Reverse Engineering Signatures
    print("[*] Pass 2: Matching against FM-1 Reverse Engineering Database...")
    fm1_matches = 0
    for e, f in functions.items():
        if f["match_source"] != "none": continue
        sig = "\n".join(f["canons"])
        if sig in fm1_canon_map:
            m = fm1_canon_map[sig]
            if m["name"] and not m["name"].startswith("fn_"):
                f["name"] = m["name"]
            f["subsystem"] = m["subsystem"]
            f["purpose"] = m["purpose"]
            f["match_source"] = "fm1_sig"
            f["confidence"] = "high"
            fm1_matches += 1
    print(f"    -> Matched {fm1_matches} functions directly to FM-1 symbols")

    # 8. Pass 3: String Cross-Reference Matching & Domain Heuristics
    print("[*] Pass 3: Matching by String References & Signatures...")
    subsystems_def = [
        ("BLE_Stack", [r"\bble\b", r"\bgatt\b", r"\badv\b", r"\bbluetooth\b", r"\bbond\b", r"03b80e5a", r"btctrler", r"btstack", r"btencry"]),
        ("MIDI_Engine", [r"\bmidi\b", r"\bchannel\b", r"midi_route", r"\bsysex\b", r"Live Seq", r"Key Seq"]),
        ("FM_Synth_DX7", [r"\bdx7\b", r"\bfm\b", r"\boperator\b", r"\bpatch\b", r"\bvoice\b", r"\bosc\b", r"\bsin\b", r"\bmsfa\b", r"\bdexed\b"]),
        ("Audio_DAC_I2S", [r"\baudio\b", r"\bi2s\b", r"\bdac\b", r"audio_dev", r"sincoaudio", r"audio_encoder", r"usr_audio_task", r"audio_cmd", r"audio_server"]),
        ("Sequencer_Arp", [r"\bseq\b", r"\bsequence\b", r"\barp\b", r"\barpeggiator\b", r"Enable SEQ", r"Drum Seq", r"note repeat"]),
        ("Hardware_UI", [r"\bkey\b", r"\bkeys\b", r"\bpad\b", r"\bled\b", r"\bdisplay\b", r"\bbutton\b", r"\bwheel\b", r"\btouch\b", r"\bencoder\b", r"PAD 1-63", r"PAD BANK", r"Key Chn", r"Pad Chn"]),
        ("USB_Controller", [r"\busb\b", r"\buac\b", r"\bendpoint\b", r"\bdescriptor\b", r"\bhid\b", r"usb_update_mode", r"USB Rec"]),
        ("Storage_JLFS", [r"\bjlfs\b", r"\bflash\b", r"\bspi\b", r"\bconfig\b", r"\bsdram\b", r"sdfile", r"ota\.bin"]),
        ("System_Boot", [r"\bboot\b", r"\breset\b", r"\bclock\b", r"\birq\b", r"\bwatchdog\b", r"app_area_head"])
    ]

    string_matches = 0
    for e, f in functions.items():
        if f["match_source"] != "none": continue
        f_strings = [strings[s] for s in f["str_refs"] if s in strings]
        f_text = " ".join(f_strings).lower()
        if e == BASE_ADDR:
            f["name"] = "crt0_reset_entry"
            f["subsystem"] = "SYS_BOOT"
            f["purpose"] = "CRT0 Reset entry and memory initialization"
            f["match_source"] = "vector"
            f["confidence"] = "high"
            continue

        for sub_name, patterns in subsystems_def:
            for pat in patterns:
                if re.search(pat, f_text, re.IGNORECASE):
                    f["subsystem"] = sub_name
                    f["confidence"] = "medium"
                    f["match_source"] = "string_xref"
                    for s in f_strings:
                        clean_s = re.sub(r'[^a-zA-Z0-9_]', '_', s).strip('_')
                        if 3 <= len(clean_s) <= 24 and not clean_s.isdigit():
                            f["name"] = f"{sub_name[:4].lower()}_{clean_s}_{e:06X}"
                            f["purpose"] = f"Referenced string: {s}"
                            break
                    string_matches += 1
                    break
            if f["match_source"] != "none": break
    print(f"    -> Classified {string_matches} functions via string cross-references")

    # 9. Pass 4: Locality Interpolation (Contiguous Translation Units)
    print("[*] Pass 4: Applying Locality Interpolation across translation units...")
    GAP = 4096 # bytes
    ent = sorted(functions.keys())
    interpolated = 0
    for i, e in enumerate(ent):
        f = functions[e]
        if f["subsystem"] != "UNCLASSIFIED" and f["subsystem"] != "UNKNOWN":
            continue
        # Search left
        left = None
        j = i - 1
        while j >= 0:
            if ent[i] - ent[j] > GAP: break
            cand = functions[ent[j]]["subsystem"]
            if cand not in ("UNCLASSIFIED", "UNKNOWN", "MEMLIB", "MATHLIB"):
                left = cand
                break
            j -= 1
        # Search right
        right = None
        j = i + 1
        while j < len(ent):
            if ent[j] - ent[i] > GAP: break
            cand = functions[ent[j]]["subsystem"]
            if cand not in ("UNCLASSIFIED", "UNKNOWN", "MEMLIB", "MATHLIB"):
                right = cand
                break
            j += 1
        target_sub = None
        if left and right and left == right:
            target_sub = left
        elif left and not right:
            target_sub = left
        elif right and not left:
            target_sub = right
        elif left and right:
            target_sub = left
        if target_sub:
            f["subsystem"] = target_sub
            f["match_source"] = "locality"
            f["confidence"] = "inferred"
            f["purpose"] = f"Inferred from neighboring translation unit ({target_sub})"
            interpolated += 1
    print(f"    -> Interpolated {interpolated} functions by translation unit locality")

    # Summary Statistics
    subsystem_counts = Counter(f["subsystem"] for f in functions.values())
    print("\n" + "=" * 50)
    print("  SMK-37 Pro Subsystem Breakdown")
    print("=" * 50)
    for sub, cnt in subsystem_counts.most_common():
        print(f"  {sub:<20}: {cnt:4d} functions")

    # 10. Write output files
    os.makedirs(OUT_DIR, exist_ok=True)
    csv_path = os.path.join(OUT_DIR, "functions_catalog.csv")
    print(f"\n[*] Emitting {csv_path}...")
    with open(csv_path, "w", encoding="utf-8") as f_csv:
        f_csv.write("address,size,name,subsystem,confidence,source,n_insns,callers_count,callees_count,purpose\n")
        for e in entries:
            f = functions[e]
            purp = f['purpose'].replace(',', ' ')
            f_csv.write(f"0x{e:08X},{f['size']},{f['name']},{f['subsystem']},{f['confidence']},{f['match_source']},{f['ninsns']},{len(f['callers'])},{len(f['callees'])},\"{purp}\"\n")

    json_path = os.path.join(OUT_DIR, "firmware_structure.json")
    print(f"[*] Emitting {json_path}...")
    out_db = {
        "base_address": f"0x{BASE_ADDR:08X}",
        "code_end": f"0x{code_end:08X}",
        "code_size": code_size,
        "total_functions": len(functions),
        "subsystem_counts": dict(subsystem_counts),
        "functions": {
            f"0x{e:08X}": {
                "name": functions[e]["name"],
                "subsystem": functions[e]["subsystem"],
                "confidence": functions[e]["confidence"],
                "source": functions[e]["match_source"],
                "purpose": functions[e]["purpose"],
                "size": functions[e]["size"],
                "n_insns": functions[e]["ninsns"],
                "callers": [f"0x{c:08X}" for c in functions[e]["callers"]],
                "callees": [f"0x{c:08X}" for c in functions[e]["callees"]],
                "strings": [strings[s] for s in functions[e]["str_refs"] if s in strings]
            }
            for e in entries
        }
    }
    with open(json_path, "w", encoding="utf-8") as f_json:
        json.dump(out_db, f_json, indent=2)

    print("[OK] Complete cross-reference and classification accomplished!")
    return 0

if __name__ == "__main__":
    sys.exit(main())
