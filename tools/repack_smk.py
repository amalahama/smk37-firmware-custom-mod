#!/usr/bin/env python3
"""repack_smk.py — Repacker for M-VAVE SMK-37 Pro Custom Firmware (.fwsc)

Reconstructs valid, flashable .fwsc firmware from components:
  1. Patches decrypted app.bin (BLE MIDI advertisement fix, optional version bump)
  2. Updates JLFS app.bin entry CRC and app_area_head data CRC
  3. Re-encrypts App Area with JieLi SFC cipher (chipkey 0x980F)
  4. Updates UFW container (flash.bin CRC, entry list CRC, header CRC)
  5. Reinterleaves marker bytes across 36 blocks
  6. Emits flashable custom .fwsc file
"""

import sys
import struct
import hashlib
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
JLTECH_DIR = REPO_DIR / "FM-1-RE" / "3rd-party" / "jl-misctools" / "firmware"
sys.path.insert(0, str(REPO_DIR))
sys.path.insert(0, str(SCRIPT_DIR))
if JLTECH_DIR.exists():
    sys.path.insert(0, str(JLTECH_DIR))

from jltech.crc import jl_crc16
from jltech.cipher import jl_enc_cipher, jl_sfc_cipher
from tools.unpack_smk import deinterleave_fwsc, decode_marker_name


CHIPKEY_SMK37 = 0x980F
APP_BASE = 0x4000
APP_BIN_OFFSET = 0x4120
APP_BIN_SIZE = 0x974B8
APP_AREA_SIZE = 0x97757
APP_ENC_SIZE = 0x97760  # aligned to 32 bytes


def patch_app_binary(
    app_bytes: bytearray,
    apply_adv_fix: bool = False,
    apply_smp_fix: bool = True,
    apply_secondary_adv_bypass: bool = True,
    target_version: str = "020"
) -> tuple[bytearray, dict]:
    """Applies surgical patches to decrypted app.bin."""
    changes = {}

    # Patch 1: (REVERTED/DISABLED) BLE Advertising pointer at offset 0x00075E
    # The original instruction 05 f1 95 26 constructs M-VAVE proprietary 0xAE advertising block.
    # Modifying it breaks M-VAVE App discovery and standard BLE negotiation!
    if apply_adv_fix:
        adv_ptr_off = 0x00075E
        orig_bytes = bytes(app_bytes[adv_ptr_off : adv_ptr_off + 4])
        if orig_bytes == bytes.fromhex("05 f1 95 26"):
            app_bytes[adv_ptr_off : adv_ptr_off + 4] = bytes.fromhex("05 f1 75 25")
            changes["adv_ptr_fix"] = {
                "offset": hex(adv_ptr_off),
                "old": orig_bytes.hex(),
                "new": "05f17525",
                "desc": "Redirected BLE adv UUID pointer"
            }

    # Patch 2: Version bump "SMK-37 Pro_016" -> target_version (e.g. "020")
    if target_version:
        for v_off in [0x05837F, 0x0587CC]:
            v_str = bytes(app_bytes[v_off : v_off + 14])
            if v_str.startswith(b"SMK-37 Pro_"):
                new_v_str = f"SMK-37 Pro_{target_version}".encode('ascii')
                app_bytes[v_off : v_off + len(new_v_str)] = new_v_str
                changes[f"version_bump_{hex(v_off)}"] = {
                    "offset": hex(v_off),
                    "old": v_str.decode('ascii', errors='replace'),
                    "new": new_v_str.decode('ascii')
                }

    # Patch 3: BLE Connection Parameters Optimization for Host/Central Stability (Woovebox, etc.)
    # Stock 016 has supervision timeout = 1000ms (0x64), which causes link-loss on minor RF jitter or ESP32 scheduling.
    # Also intervals (min=7.5ms, max=11.25ms / min=15ms, max=15ms) are overly rigid.
    # We increase supervision timeout to 4000ms (0x0190 = 400 * 10ms) and relax interval ceiling.
    conn_params_off = 0x05839E
    orig_params = bytes(app_bytes[conn_params_off : conn_params_off + 16])
    expected_stock_params = bytes.fromhex("06000900000064000c000c0000006400")
    if orig_params == expected_stock_params:
        # Set 1: min=7.5ms, max=20ms, lat=0, timeout=4000ms (0x0190)
        # Set 2: min=15ms, max=30ms, lat=0, timeout=4000ms (0x0190)
        new_params = bytes.fromhex("06001000000090010c00180000009001")
        app_bytes[conn_params_off : conn_params_off + 16] = new_params
        changes["ble_conn_params_stabilization"] = {
            "offset": hex(conn_params_off),
            "old": orig_params.hex(),
            "new": new_params.hex(),
            "desc": "Supervision timeout increased from 1000ms to 4000ms, intervals relaxed (7.5-20ms / 15-30ms)"
        }

    # Patch 4: Security Manager Protocol (SMP) - Enforce "Just Works" with Bonding (No MITM, No PIN, NoInputNoOutput)
    # JieLi stack defaults to auth_req = 51 (0x33: MITM + Bonding) and IO Capability = 5 (Keyboard Display).
    # Embedded Centrals like Woovebox have NoInputNoOutput and no keyboard, failing/timing out MITM pairing.
    # We set auth_req = 1 (BONDING enabled, MITM disabled) and IO Capability = 3 (NO_INPUT_NO_OUTPUT).
    if apply_smp_fix:
        # 4a: ble_sm_auth_req_default at 0x087446: change to 'r2 = 1' (42 21) -> auth_req = 0x01 (Bonding without MITM)
        auth_req_off = 0x087446
        if bytes(app_bytes[auth_req_off : auth_req_off + 2]) in [bytes.fromhex("4a33"), bytes.fromhex("4220")]:
            orig_auth = bytes(app_bytes[auth_req_off : auth_req_off + 2])
            app_bytes[auth_req_off : auth_req_off + 2] = bytes.fromhex("4221")
            changes["smp_auth_req_just_works"] = {
                "offset": hex(auth_req_off),
                "old": f"{orig_auth.hex()}",
                "new": "4221 (r2 = 1)",
                "desc": "Default auth_req set to 0x01 (No MITM, Bonding enabled -> Just Works with Bond storage)"
            }

        # 4b: ble_sm_param_pair_set at 0x08758a: change 'r2 = 5' (42 25) to 'r2 = 3' (42 23) -> NoInputNoOutput
        io_cap_off = 0x08758A
        if bytes(app_bytes[io_cap_off : io_cap_off + 2]) in [bytes.fromhex("4225"), bytes.fromhex("4223")]:
            orig_io = bytes(app_bytes[io_cap_off : io_cap_off + 2])
            app_bytes[io_cap_off : io_cap_off + 2] = bytes.fromhex("4223")
            changes["smp_io_cap_no_input_no_output"] = {
                "offset": hex(io_cap_off),
                "old": f"{orig_io.hex()}",
                "new": "4223 (r2 = 3)",
                "desc": "IO Capability set to 3 (IO_CAPABILITY_NO_INPUT_NO_OUTPUT)"
            }

        # 4c: ble_sm_auth_flags_or at 0x0875c4: change 'r1 |= 256' (31 28) to 'nop' (00 00) -> remove SC requirement
        sc_flag_off = 0x0875C4
        if bytes(app_bytes[sc_flag_off : sc_flag_off + 2]) in [bytes.fromhex("3128"), bytes.fromhex("0000")]:
            orig_sc = bytes(app_bytes[sc_flag_off : sc_flag_off + 2])
            app_bytes[sc_flag_off : sc_flag_off + 2] = bytes.fromhex("0000")
            changes["smp_sc_flag_removed"] = {
                "offset": hex(sc_flag_off),
                "old": f"{orig_sc.hex()}",
                "new": "0000 (nop)",
                "desc": "Removed mandatory Secure Connections requirement"
            }

    # Patch 5: Suppress Secondary BLE Advertising on BLE-MIDI CCCD Subscription
    # In stock 016, when a Central writes CCCD 0x2902 (handle 115 / 0x73) to enable MIDI notifications,
    # routine 0x0200138A calls ble_set_adv_enable(1) at 0x020013E8 to launch secondary advertising on
    # radio channels 37, 38, 39 for a second slot.
    # This causes RF collisions, timing jitter, and confuses Woovebox's host scanner into reconnect loops.
    # At offset 0x0013D2, changing 'if (r0 == 0) goto 156' (20 4e) to unconditional 'goto 156' (24 8e)
    # jumps directly to 0x02001470 (clean return 0), completely bypassing secondary advertising!
    if apply_secondary_adv_bypass:
        adv_bypass_off = 0x0013D2
        if bytes(app_bytes[adv_bypass_off : adv_bypass_off + 2]) in [bytes.fromhex("204e"), bytes.fromhex("248e")]:
            orig_adv = bytes(app_bytes[adv_bypass_off : adv_bypass_off + 2])
            app_bytes[adv_bypass_off : adv_bypass_off + 2] = bytes.fromhex("248e")
            changes["secondary_adv_bypass"] = {
                "offset": hex(adv_bypass_off),
                "old": f"{orig_adv.hex()}",
                "new": "248e (goto 156)",
                "desc": "Bypass secondary BLE advertising trigger on BLE-MIDI CCCD notification enable"
            }

    # Patch 6: Unconditional BLE-MIDI Notification Transmission
    # In routine 0x02000AD4, the firmware checks if the client has written CCCD = 1:
    # 0x02000AE8: call 0x02007DB14 (check CCCD)
    # 0x02000AEE: if (r0 == 0) goto 0x02000B16 (abort and return 5 if CCCD != 1)
    # When reconnecting to an embedded host (like Woovebox) or if CCCD is not re-written after link establishment,
    # r0 is 0 and the firmware silences all MIDI note notifications!
    # NOPing 0x02000AEE (00 53 -> 00 00) makes notification transmission unconditional when connected.
    notif_bypass_off = 0x000AEE
    if bytes(app_bytes[notif_bypass_off : notif_bypass_off + 2]) in [bytes.fromhex("0053"), bytes.fromhex("0000")]:
        orig_notif = bytes(app_bytes[notif_bypass_off : notif_bypass_off + 2])
        app_bytes[notif_bypass_off : notif_bypass_off + 2] = bytes.fromhex("0000")
        changes["unconditional_ble_midi_notif"] = {
            "offset": hex(notif_bypass_off),
            "old": f"{orig_notif.hex()}",
            "new": "0000 (nop)",
            "desc": "Unconditional BLE-MIDI notifications (prevents silent note suppression on reconnect)"
        }

    # Patch 7: Fresh Unique BLE MAC Address Generation (Bypass stale Host Bond / NVS Cache)
    # The firmware caches its static MAC address in VM storage key 102 (0x66).
    # If a Central (like Woovebox) has cached a stale, failed, or half-bonded security state for this MAC,
    # it persistently fails encryption / GATT routing on reconnect.
    # Changing the VM key from 102 (58 26) to 108 (58 2c) forces the firmware to generate and register
    # a brand new, clean BLE MAC address, completely bypassing any stale bond/NVS cache on the Host!
    for mac_off in [0x0035CE, 0x003668]:
        if bytes(app_bytes[mac_off : mac_off + 2]) in [bytes.fromhex("5826"), bytes.fromhex("582c")]:
            orig_mac_op = bytes(app_bytes[mac_off : mac_off + 2])
            app_bytes[mac_off : mac_off + 2] = bytes.fromhex("582c")
            changes[f"fresh_mac_key_{hex(mac_off)}"] = {
                "offset": hex(mac_off),
                "old": f"{orig_mac_op.hex()} (r0 = 102)",
                "new": "582c (r0 = 108)",
                "desc": "Redirect VM MAC key to 108 (forces fresh MAC generation, clearing host bond cache)"
            }

    return app_bytes, changes


def repack_firmware(
    stock_fwsc_path: Path,
    output_fwsc_path: Path,
    apply_patches: bool = True,
    bump_version: bool = True,
    target_version: str = "019",
    custom_app_bin: bytes = None
):
    print(f"Reading stock firmware: {stock_fwsc_path}...")
    stock_fwsc = stock_fwsc_path.read_bytes()
    stock_sha = hashlib.sha256(stock_fwsc).hexdigest()
    print(f"  Stock SHA-256: {stock_sha}")

    # Step 1: Deinterleave
    logical_ufw, markers, num_blocks = deinterleave_fwsc(stock_fwsc)
    print(f"  Deinterleaved: {num_blocks} blocks, {len(logical_ufw)} logical bytes.")

    # Step 2: Parse UFW Header
    hdr_bytes = bytearray(logical_ufw[:0x40])
    jl_enc_cipher(hdr_bytes, 0, 0x40, key=0xFFFF)
    hdrcrc, listcrc, imgsize, numents, wa3, wa4, chipname = struct.unpack_from('<HHIHHI48s', hdr_bytes, 0)

    headersize = 0x40 + numents * 0x50
    full_hdr = bytearray(logical_ufw[:headersize])
    for off in range(0x40, headersize, 0x50):
        jl_enc_cipher(full_hdr, off, 0x50, key=0xFFFF)

    entries = []
    flash_entry_idx = None
    for i, off in enumerate(range(0x40, headersize, 0x50)):
        etype, eindex, edcrc, ewa1, eoffset, esize, esize2, ewa2, ename_b = struct.unpack_from('<HHHHIII44s16s', full_hdr, off)
        ename = ename_b.split(b'\x00')[0].decode('ascii')
        entries.append({
            "hdr_off": off,
            "name": ename,
            "type": etype,
            "index": eindex,
            "data_crc": edcrc,
            "offset": eoffset,
            "size": esize,
            "size2": esize2,
            "raw_hdr": full_hdr[off : off + 0x50]
        })
        if ename == "flash.bin":
            flash_entry_idx = i

    if flash_entry_idx is None:
        raise RuntimeError("flash.bin entry not found in UFW container!")

    flash_entry = entries[flash_entry_idx]
    flash_data = bytearray(logical_ufw[flash_entry["offset"] : flash_entry["offset"] + flash_entry["size"]])

    if apply_patches:
        print("\nDecrypting App Area in flash.bin with SFC cipher (chipkey 0x980F)...")
        # Decrypt App Area
        jl_sfc_cipher(flash_data, APP_BASE, APP_ENC_SIZE, APP_BASE, CHIPKEY_SMK37)

        # Extract app.bin or use custom_app_bin
        if custom_app_bin is not None:
            app_bin = bytearray(custom_app_bin)
            print(f"  Using custom provided app.bin: {len(app_bin)} bytes")
        else:
            app_bin = bytearray(flash_data[APP_BIN_OFFSET : APP_BIN_OFFSET + APP_BIN_SIZE])
            print(f"  Extracted app.bin: {len(app_bin)} bytes, original CRC: 0x{jl_crc16(app_bin):04X}")

        # Apply surgical patches
        app_bin, changes = patch_app_binary(app_bin, target_version=target_version if bump_version else None)
        print("  Patches applied:")
        for k, v in changes.items():
            print(f"    - {k}: {v}")

        new_app_crc = jl_crc16(app_bin)
        print(f"  Patched app.bin CRC: 0x{new_app_crc:04X}")

        # Put patched app.bin back into flash_data
        flash_data[APP_BIN_OFFSET : APP_BIN_OFFSET + APP_BIN_SIZE] = app_bin

        # Update app.bin JLFS entry at 0x4020
        # Layout of 32-byte JLFS entry: <H (hcrc) + <H (data_crc) + IIBBH16s (hdr payload)
        ahcrc, ahdr = struct.unpack_from('<H30s', flash_data, 0x4020)
        # Update data_crc (bytes 0..2 of ahdr)
        new_ahdr = struct.pack('<H', new_app_crc) + ahdr[2:]
        new_ahcrc = jl_crc16(new_ahdr)
        flash_data[0x4020 : 0x4040] = struct.pack('<H30s', new_ahcrc, new_ahdr)

        # Update app_area_head JLFS entry at 0x4000
        # data_crc covers flash_data[0x4020 : 0x4000 + APP_AREA_SIZE]
        app_area_data = flash_data[0x4020 : 0x4000 + APP_AREA_SIZE]
        new_area_crc = jl_crc16(app_area_data)
        print(f"  Updated app_area_head data CRC: 0x{new_area_crc:04X}")

        hhcrc, hhdr = struct.unpack_from('<H30s', flash_data, 0x4000)
        new_hhdr = struct.pack('<H', new_area_crc) + hhdr[2:]
        new_hhcrc = jl_crc16(new_hhdr)
        flash_data[0x4000 : 0x4020] = struct.pack('<H30s', new_hhcrc, new_hhdr)

        # Re-encrypt App Area
        print("Re-encrypting App Area with SFC cipher (chipkey 0x980F)...")
        jl_sfc_cipher(flash_data, APP_BASE, APP_ENC_SIZE, APP_BASE, CHIPKEY_SMK37)

    new_flash_crc = jl_crc16(flash_data)
    print(f"\nFinal flash.bin CRC: 0x{new_flash_crc:04X}")

    # Step 3: Rebuild logical UFW container
    new_logical = bytearray(logical_ufw)
    # Put updated flash_data
    new_logical[flash_entry["offset"] : flash_entry["offset"] + flash_entry["size"]] = flash_data

    # Update flash.bin entry in UFW header
    hdr_off = flash_entry["hdr_off"]
    etype, eindex, edcrc, ewa1, eoffset, esize, esize2, ewa2, ename_b = struct.unpack_from('<HHHHIII44s16s', full_hdr, hdr_off)
    full_hdr[hdr_off : hdr_off + 0x50] = struct.pack('<HHHHIII44s16s', etype, eindex, new_flash_crc, ewa1, eoffset, esize, esize2, ewa2, ename_b)

    # Scramble entry headers with key 0xFFFF
    scrambled_entries = bytearray(full_hdr[0x40:headersize])
    for off in range(0, len(scrambled_entries), 0x50):
        jl_enc_cipher(scrambled_entries, off, 0x50, key=0xFFFF)

    # Recalculate listcrc over scrambled entry descriptors
    new_listcrc = jl_crc16(scrambled_entries)

    # Update UFW top header
    # struct: <HHIHHI48s (hdrcrc, listcrc, imgsize, numents, wa3, wa4, chipname)
    top_hdr_body = struct.pack('<HIHHI48s', new_listcrc, len(new_logical), numents, wa3, wa4, chipname)
    new_hdrcrc = jl_crc16(top_hdr_body)
    new_top_hdr = struct.pack('<H', new_hdrcrc) + top_hdr_body

    # Scramble top header with key 0xFFFF
    scrambled_top_hdr = bytearray(new_top_hdr)
    jl_enc_cipher(scrambled_top_hdr, 0, 0x40, key=0xFFFF)

    new_logical[:0x40] = scrambled_top_hdr
    new_logical[0x40:headersize] = scrambled_entries

    # Step 4: Re-interleave marker bytes
    if apply_patches and bump_version and target_version and len(markers) > 13:
        target_name = f"SMK-37 Pro_{target_version}"
        for i, c in enumerate(target_name):
            if i < len(markers):
                markers[i] = (ord(c) + i + 1) & 0xFF
        print(f"  Updated trailer marker to reflect version bump: '{decode_marker_name(markers)}'")

    print(f"Reinterleaving {num_blocks} blocks with marker bytes...")
    reinterleaved = bytearray()
    for i in range(num_blocks):
        chunk = new_logical[i * 0x2F : (i + 1) * 0x2F]
        reinterleaved += chunk
        reinterleaved.append(markers[i])
    reinterleaved += new_logical[num_blocks * 0x2F :]

    out_bytes = bytes(reinterleaved)
    output_fwsc_path.parent.mkdir(parents=True, exist_ok=True)
    output_fwsc_path.write_bytes(out_bytes)

    out_sha = hashlib.sha256(out_bytes).hexdigest()
    print(f"\nRepack complete! Successfully written: {output_fwsc_path}")
    print(f"  Output size: {len(out_bytes)} bytes")
    print(f"  Output SHA-256: {out_sha}")

    if not apply_patches:
        if out_sha == stock_sha:
            print("  [PASS] Bit-for-bit exact match with stock .fwsc!")
        else:
            print("  [FAIL] SHA-256 mismatch with stock .fwsc!")

    return output_fwsc_path


if __name__ == "__main__":
    stock_path = REPO_DIR / "stock_firmware" / "SMK-37_Pro_016.fwsc"
    if not stock_path.exists():
        stock_path = REPO_DIR / "smk-37-pro-docs" / "firmware" / "smk37pro" / "SMK-37_Pro_016.fwsc"
    
    # Test 1: Bit-for-bit roundtrip test
    print("=================== TEST 1: BIT-FOR-BIT ROUNDTRIP ===================")
    test_roundtrip = REPO_DIR / "firmware_work" / "test_roundtrip_016.fwsc"
    repack_firmware(stock_path, test_roundtrip, apply_patches=False)

    # Test 2: Custom firmware V018 (reverts erroneous 0x75E adv patch, clean version bump)
    print("\n=================== TEST 2: CUSTOM FIRMWARE V018 ===================")
    custom_path_018 = REPO_DIR / "firmware_work" / "SMK-37_Pro_custom_018.fwsc"
    repack_firmware(stock_path, custom_path_018, apply_patches=True, bump_version=True, target_version="018")

    # Test 3: Custom firmware V019 (Woovebox BLE stability: 4000ms supervision timeout + relaxed intervals)
    print("\n=================== TEST 3: CUSTOM FIRMWARE V019 ===================")
    custom_path_019 = REPO_DIR / "firmware_work" / "SMK-37_Pro_custom_019.fwsc"
    repack_firmware(stock_path, custom_path_019, apply_patches=True, bump_version=True, target_version="019")

    # Test 4: Custom firmware V020 (SMP Just Works + Secondary Advertising Suppression + 4000ms supervision timeout)
    print("\n=================== TEST 4: CUSTOM FIRMWARE V020 ===================")
    custom_path_020 = REPO_DIR / "firmware_work" / "SMK-37_Pro_custom_020.fwsc"
    repack_firmware(stock_path, custom_path_020, apply_patches=True, bump_version=True, target_version="020")

    # Test 5: Custom firmware V021 (Unconditional BLE-MIDI notifications + Just Works Bonding)
    print("\n=================== TEST 5: CUSTOM FIRMWARE V021 ===================")
    custom_path_021 = REPO_DIR / "firmware_work" / "SMK-37_Pro_custom_021.fwsc"
    repack_firmware(stock_path, custom_path_021, apply_patches=True, bump_version=True, target_version="021")

    # Test 6: Custom firmware V022 (Fresh MAC address + Unconditional notifications + Just Works Bonding)
    print("\n=================== TEST 6: CUSTOM FIRMWARE V022 ===================")
    custom_path_022 = REPO_DIR / "firmware_work" / "SMK-37_Pro_custom_022.fwsc"
    repack_firmware(stock_path, custom_path_022, apply_patches=True, bump_version=True, target_version="022")



