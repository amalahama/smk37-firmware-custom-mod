#!/usr/bin/env python3
"""unpack_smk.py — Robust firmware unpacker for M-VAVE SMK-37 Pro / Elite / FM-1 (.fwsc)

Handles both 20-block legacy fwsc and 36-block extended fwsc (used in V16+).
Extracts:
  - UFW container components (flash.bin, ota.bin, isd_config.ini, etc.)
  - SPL (uboot.boot)
  - Decrypted app.bin (JieLi SFC cipher with chipkey 0x980F)
  - cfg_tool.bin, cfg, eq_cfg_hw.bin
  - jlfw.yaml metadata
"""

import os
import sys
import struct
import argparse
from pathlib import Path
import yaml

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_DIR = SCRIPT_DIR.parent
JLTECH_DIR = REPO_DIR / "FM-1-RE" / "3rd-party" / "jl-misctools" / "firmware"
sys.path.insert(0, str(SCRIPT_DIR))
if JLTECH_DIR.exists():
    sys.path.insert(0, str(JLTECH_DIR))

from jltech.crc import jl_crc16
from jltech.cipher import jl_enc_cipher, jl_sfc_cipher
from jltech.chipkeybin import chipkeybin_decode
from jltech.utils import align_to, nulltermstr


class JLFSEntry:
    def __init__(self, buff, off=0, database=0, data_after_header=False):
        hcrc, hdr = struct.unpack_from('<H30s', buff, off)
        if jl_crc16(hdr) != hcrc:
            raise ValueError(f'JLFS entry header CRC mismatch at 0x{off:X}: hdr CRC 0x{hcrc:04X} != calc 0x{jl_crc16(hdr):04X}')

        edcrc, eoff, esize, eflags, eresvd, eindex, ename = struct.unpack('<HIIBBH16s', hdr)

        self.hdr_off  = off
        self.data_crc = edcrc
        self.offset   = eoff
        self.size     = esize
        self.flags    = eflags
        self.resvd    = eresvd
        self.index    = eindex
        self.raw_name = ename

        if data_after_header:
            self.data_offset = self.hdr_off + 32
            self.data_size = self.hdr_off + self.size - self.data_offset
        else:
            self.data_offset = self.offset + database
            self.data_size = self.size

        self.name = nulltermstr(ename, 'ascii')

    def __str__(self):
        return f'<JLFS Entry @{self.hdr_off:08X} - {self.data_crc:04X} @{self.offset:08X}/{self.data_offset:08X} ({self.size:10}/{self.data_size:10}) - {self.flags:02X}/{self.resvd:02X} / {self.index} -- "{self.name}">'


class JLFSIterator:
    def __init__(self, buff, base, off=0, key=None, sfc=False):
        self.buff = buff
        self.baseaddr = base
        self.offset = off
        self.key = key
        self.is_sfc_area = sfc
        self.is_over = False
        self.dec_off = self.baseaddr

    def __iter__(self):
        return self

    def __next__(self):
        if self.is_over:
            raise StopIteration

        entoff = self.baseaddr + self.offset

        if self.key is not None:
            if self.is_sfc_area:
                next_off = align_to(entoff + 32, 32)
                if self.dec_off < next_off:
                    num = next_off - self.dec_off
                    jl_sfc_cipher(self.buff, self.dec_off, num, self.baseaddr, self.key)
                    self.dec_off += num
            else:
                jl_enc_cipher(self.buff, entoff, 32, self.key)

        entry = JLFSEntry(self.buff, entoff, self.baseaddr, self.is_sfc_area)
        self.is_over = entry.index != 0

        if self.is_sfc_area:
            self.offset += entry.size
            if self.key is not None:
                next_off = self.baseaddr + self.offset
                if not self.is_over:
                    next_off = align_to(next_off + 32, 32)
                if self.dec_off < next_off:
                    num = next_off - self.dec_off
                    jl_sfc_cipher(self.buff, self.dec_off, num, self.baseaddr, self.key)
                    self.dec_off += num
        else:
            self.offset += 32

        return entry


def descramble_bankcb(data, base, key):
    bankcount = 1
    index = 0
    while index < bankcount:
        hdroff = base + index * 16
        jl_enc_cipher(data, hdroff, 16, key)
        hdr, hcrc = struct.unpack_from('<14sH', data, hdroff)
        if jl_crc16(hdr) != hcrc:
            raise ValueError(f'Bank {index} header CRC mismatch.')
        bankid, banksize, bankload, bankoff, bankcrc = struct.unpack('<HHIIH', hdr)
        if index == 0:
            bankcount = bankid
        jl_enc_cipher(data, base + bankoff, banksize, key)
        index += 1


def deinterleave_fwsc(raw_bytes: bytes) -> tuple[bytes, list[int], int]:
    num_blocks = 0
    markers = []
    total_possible = len(raw_bytes) // 0x30

    for i in range(total_possible):
        val = raw_bytes[i * 0x30 + 0x2F]
        if i < 20 or val == 0x7D:
            num_blocks = i + 1
            markers.append(val)
        else:
            break

    logical = bytearray()
    for i in range(num_blocks):
        logical += raw_bytes[i * 0x30 : i * 0x30 + 0x2F]
    logical += raw_bytes[num_blocks * 0x30 :]

    return bytes(logical), markers, num_blocks


def decode_marker_name(markers: list[int]) -> str:
    chars = []
    for i, m in enumerate(markers):
        if m == 0x7D:
            break
        c = (m - i - 1) & 0xFF
        if 32 <= c <= 126:
            chars.append(chr(c))
        else:
            break
    return "".join(chars)


def unpack_fwsc(input_file: Path, out_dir: Path):
    print(f"Reading {input_file}...")
    raw = input_file.read_bytes()
    print(f"  Raw file size: {len(raw)} bytes")

    logical, markers, num_blocks = deinterleave_fwsc(raw)
    prod_name = decode_marker_name(markers)
    print(f"  Deinterleaved {num_blocks} blocks ({num_blocks * 0x30} bytes -> {num_blocks * 0x2F} bytes).")
    print(f"  Detected identity from markers: '{prod_name}'")
    print(f"  Logical file size: {len(logical)} bytes")

    out_dir.mkdir(parents=True, exist_ok=True)
    raw_dir = out_dir / "raw_components"
    raw_dir.mkdir(exist_ok=True)
    top_dir = out_dir / "top"
    top_dir.mkdir(exist_ok=True)
    files_dir = out_dir / "files"
    files_dir.mkdir(exist_ok=True)

    hdr_bytes = bytearray(logical[:0x40])
    jl_enc_cipher(hdr_bytes, 0, 0x40, key=0xFFFF)
    hdrcrc, listcrc, imgsize, numents, wa3, wa4, chipname = struct.unpack_from('<HHIHHI48s', hdr_bytes, 0)
    chipname_str = chipname.split(b'\x00')[0].decode('ascii', errors='replace')
    print(f"  UFW Chip Name: {chipname_str}")
    print(f"  UFW Number of Entries: {numents}")

    headersize = 0x40 + numents * 0x50
    full_hdr = bytearray(logical[:headersize])
    for off in range(0x40, headersize, 0x50):
        jl_enc_cipher(full_hdr, off, 0x50, key=0xFFFF)

    entries = []
    flash_bin = None

    for off in range(0x40, headersize, 0x50):
        etype, eindex, edcrc, ewa1, eoffset, esize, esize2, ewa2, ename_b = \
            struct.unpack_from('<HHHHIII44s16s', full_hdr, off)
        ename = ename_b.split(b'\x00')[0].decode('ascii', errors='replace')
        ent_data = logical[eoffset : eoffset + esize]
        crc_ok = jl_crc16(ent_data) == edcrc
        print(f"  -> Entry: {ename:<15} (type={etype:<3}, offset=0x{eoffset:06X}, size={esize:<7} bytes, CRC_match={crc_ok})")

        (raw_dir / ename).write_bytes(ent_data)
        entries.append({
            "name": ename,
            "type": etype,
            "offset": eoffset,
            "size": esize,
            "crc_match": crc_ok
        })

        if etype == 0 or ename == "flash.bin":
            flash_bin = bytearray(ent_data)

    if not flash_bin:
        raise RuntimeError("flash.bin entry not found in UFW container!")

    headerkey = 0xFFFF
    baseoff = None
    for off in [0, 0x1000, 0x10000, 0x80000, 0x100000]:
        cand = flash_bin[off : off + 32]
        jl_enc_cipher(cand, 0, len(cand), headerkey)
        hcrc, hdata = int.from_bytes(cand[:2], 'little'), cand[2:]
        if hcrc != 0 and jl_crc16(hdata) == hcrc:
            baseoff = off
            break

    if baseoff is None:
        raise RuntimeError("Could not find flash header in flash.bin!")

    print(f"\nFlash base offset: 0x{baseoff:X}")
    # Decrypt flash header (bytes 0..3 and 8..15 are scrambled, 4..7 and 16..31 are plaintext)
    header = bytearray(cand)
    jl_enc_cipher(header, 0, len(header), headerkey)
    header = header[:4] + flash_bin[baseoff+4:baseoff+8] + header[8:16] + flash_bin[baseoff+16:baseoff+32]
    fhcrc, fburnersz, fvid, fflashsz, ffsver, fblockalign, fresvd, fspecopt, fpid = \
        struct.unpack('<HH4sIBBBB16s', header)
    pid_str = fpid.split(b'\xff')[0].decode('ascii', errors='replace')
    vid_str = fvid.split(b'\x00')[0].decode('ascii', errors='replace')
    print(f"  PID: {pid_str}, VID: {vid_str}, Flash size: 0x{fflashsz:X}")

    chipkey = None
    appbase = None
    appfiles = []
    resfiles = []

    for i, ent in enumerate(JLFSIterator(flash_bin, baseoff, 32, key=headerkey)):
        print(f"(top) {ent}")
        fout = top_dir / ent.name

        if i == 0:
            descramble_bankcb(flash_bin, ent.data_offset, headerkey)
            fout.write_bytes(flash_bin[ent.data_offset : ent.data_offset + ent.data_size])
        elif ent.flags == 0x81:
            if ent.name == "app_dir_head":
                appbase = ent.data_offset
            continue
        elif ent.flags & 0x10:
            continue
        elif ent.name == "isd_config.ini":
            ckdata, ckcrc = struct.unpack_from('<32sH', flash_bin, ent.data_offset)
            if jl_crc16(ckdata) == ckcrc:
                chipkey = chipkeybin_decode(ckdata)
                print(f"  Chipkey decoded from isd_config.ini: 0x{chipkey:04X} ({chipkey})")
            fout.write_bytes(flash_bin[ent.data_offset : ent.data_offset + ent.data_size])
        else:
            fout.write_bytes(flash_bin[ent.data_offset : ent.data_offset + ent.data_size])

    if appbase is None:
        raise RuntimeError("app_dir_head not found in JLFS top directory!")

    print(f"\nParsing App Area at 0x{appbase:X} with chipkey 0x{chipkey:04X}...")
    entry_point = None
    for i, ent in enumerate(JLFSIterator(flash_bin, appbase, 0, key=chipkey, sfc=True)):
        if i == 0:
            print('(App Area Head)', ent)
            entry_point = ent.offset
            print(f'  Entry point address: 0x{entry_point:X}')

            for aent in JLFSIterator(flash_bin, ent.hdr_off, ent.data_offset - ent.hdr_off):
                print('(App)', aent)
                if aent.flags & 0x10:
                    pass
                elif aent.flags != 0x82:
                    pass
                else:
                    fpath = files_dir / aent.name
                    fpath.write_bytes(flash_bin[aent.data_offset : aent.data_offset + aent.data_size])
                    appfiles.append(str(fpath.relative_to(out_dir)))
        else:
            print('(Res)', ent)
            fpath = files_dir / ent.name
            if ent.flags & 0x10:
                pass
            elif ent.flags == 0x82:
                fpath.write_bytes(flash_bin[ent.data_offset : ent.data_offset + ent.data_size])
                resfiles.append(str(fpath.relative_to(out_dir)))
            else:
                fpath.write_bytes(flash_bin[ent.hdr_off : ent.hdr_off + ent.size])
                resfiles.append(str(fpath.relative_to(out_dir)))

                if ent.flags == 0x83:
                    extradir = files_dir / f'{ent.name}-extracted'
                    extradir.mkdir(exist_ok=True)
                    for aent in JLFSIterator(flash_bin, ent.hdr_off, ent.data_offset - ent.hdr_off):
                        print('  ====>', aent)
                        (extradir / aent.name).write_bytes(flash_bin[aent.data_offset : aent.data_offset + aent.data_size])

    manifest = {
        "format": "jl-new-fw",
        "product-name": prod_name,
        "chip-name": chipname_str,
        "chip-key": chipkey,
        "entry-point": entry_point,
        "spl": {
            "file": "top/uboot.boot",
            "compressed": False
        },
        "app-files": appfiles,
        "res-files": resfiles
    }
    with open(out_dir / "jlfw.yaml", "w") as f:
        yaml.dump(manifest, f)

    (out_dir / "decrypted_flash.bin").write_bytes(flash_bin)
    print(f"\nUnpack complete! Output written to: {out_dir}")
    app_bin_size = len((files_dir / 'app.bin').read_bytes())
    print(f"Decrypted app.bin size: {app_bin_size} bytes (0x{app_bin_size:X})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Unpack M-VAVE SMK-37 Pro / FM-1 .fwsc firmware")
    parser.add_argument("input", type=Path, help="Path to .fwsc file")
    parser.add_argument("-o", "--output", type=Path, default=Path("firmware_work/v16_unpacked"), help="Output directory")
    args = parser.parse_args()
    unpack_fwsc(args.input, args.output)
