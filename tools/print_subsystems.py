import json

db = json.load(open("firmware_work/analysis/firmware_structure.json"))
funcs = db["functions"]

for target_sub in ["BT", "USB", "MIDI", "AUDIO_OUT", "AUDIO_DSP", "Sequencer_Arp", "SYNTH_FM", "Hardware_UI"]:
    items = [(addr, f) for addr, f in funcs.items() if f["subsystem"] == target_sub and not f["name"].startswith("fn_")]
    print(f"\n=================== {target_sub} ({len(items)} identified functions) ===================")
    for addr, f in items[:8]:
        callers = len(f["callers"])
        callees = len(f["callees"])
        print(f"  {addr}  {f['name']:<30} (size={f['size']:<3}) callers={callers:<2} callees={callees:<2} - {f['purpose'][:55]}")
