#!/usr/bin/env python3
"""Extract every file from the embedded Godot 4.1 PCK of Buckshot Roulette.

Layout (Godot 4.x, format 2):
  header 100 bytes, then per file:
    path: u32 length (already 4-aligned, NUL padded) + bytes
    offset u64, size u64, md5[16], flags u32
  file data lives at (file_base + offset) inside the exe when PACK_REL_FILEBASE
  is clear (embedded pack: file_base is absolute in the executable).
"""
import hashlib
import json
import os
import struct
import sys

EXE = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\Buckshot Roulette.exe"
PCK = 0x03725E00
OUT = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\game_data"

FILE_ENCRYPTED = 1 << 0
FILE_REMOVED = 1 << 1


def read_dir(f):
    f.seek(PCK)
    hdr = f.read(100)
    magic, fmt = struct.unpack_from("<4sI", hdr, 0)
    vmaj, vmin, vpat, flags = struct.unpack_from("<IIII", hdr, 8)
    (file_base,) = struct.unpack_from("<Q", hdr, 24)
    (count,) = struct.unpack_from("<I", hdr, 96)
    assert magic == b"GDPC", magic
    assert not (flags & 1), "directory is encrypted"

    entries = []
    for _ in range(count):
        (plen,) = struct.unpack("<I", f.read(4))
        raw = f.read(plen)
        assert plen % 4 == 0, plen
        path = raw.rstrip(b"\x00").decode("utf-8")
        ofs, size = struct.unpack("<QQ", f.read(16))
        md5 = f.read(16)
        (eflags,) = struct.unpack("<I", f.read(4))
        entries.append({"path": path, "ofs": ofs, "size": size, "md5": md5, "flags": eflags})
    return entries, file_base, (vmaj, vmin, vpat), flags


def disk_name(path):
    rel = path[len("res://"):] if path.startswith("res://") else path
    return os.path.join(OUT, rel.replace("/", os.sep))


def main():
    os.makedirs(OUT, exist_ok=True)
    with open(EXE, "rb") as f:
        entries, file_base, ver, flags = read_dir(f)
        print(f"godot {ver[0]}.{ver[1]}.{ver[2]}  entries={len(entries)}  "
              f"file_base=0x{file_base:X}  flags=0x{flags:X}")

        bad = 0
        written = 0
        total = 0
        for i, e in enumerate(entries):
            if e["flags"] & FILE_REMOVED:
                continue
            if e["flags"] & FILE_ENCRYPTED:
                raise SystemExit(f"encrypted payload: {e['path']}")
            dst = disk_name(e["path"])
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            f.seek(file_base + e["ofs"])
            data = f.read(e["size"])
            got = hashlib.md5(data).digest()
            if got != e["md5"]:
                bad += 1
                print(f"  MD5 MISMATCH {e['path']} ({e['size']} bytes)")
            with open(dst, "wb") as out:
                out.write(data)
            written += 1
            total += len(data)
            if (i + 1) % 500 == 0:
                print(f"  {i + 1}/{len(entries)} ... {total / 1e6:.0f} MB")

    print(f"\nwrote {written} files, {total / 1e6:.1f} MB, md5 mismatches={bad}")
    with open(os.path.join(OUT, "..", "manifest.json"), "w", encoding="utf-8") as out:
        json.dump(
            [{"path": e["path"], "size": e["size"], "md5": e["md5"].hex(), "flags": e["flags"]}
             for e in entries], out, indent=0)
    print("wrote manifest.json")


if __name__ == "__main__":
    main()
