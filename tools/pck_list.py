#!/usr/bin/env python3
"""Parse the embedded Godot 4.1 PCK directory of a single-file Windows export.

Godot 4 pack header:
  magic 'GDPC', format_version u32, ver_major/minor/patch u32,
  pack_flags u32, file_base u64, reserved[16] u32, file_count u32
Entry:
  path (u32 len + bytes, padded to 4), offset u64, size u64, md5[16], flags u32
"""
import struct
import sys

PATH = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\Buckshot Roulette.exe"
PCK = 0x03725E00

PACK_DIR_ENCRYPTED = 1 << 0
PACK_REL_FILEBASE = 1 << 1
FILE_ENCRYPTED = 1 << 0
FILE_REMOVED = 1 << 1


def main():
    with open(PATH, "rb") as f:
        f.seek(0, 2)
        fsize = f.tell()
        f.seek(PCK)
        hdr = f.read(100)
        magic, fmt = struct.unpack_from("<4sI", hdr, 0)
        vmaj, vmin, vpat, flags = struct.unpack_from("<IIII", hdr, 8)
        (file_base,) = struct.unpack_from("<Q", hdr, 24)
        (count,) = struct.unpack_from("<I", hdr, 96)
        print(f"magic={magic!r} format={fmt} godot={vmaj}.{vmin}.{vpat}")
        print(f"flags=0x{flags:X} dir_encrypted={bool(flags & PACK_DIR_ENCRYPTED)} "
              f"rel_filebase={bool(flags & PACK_REL_FILEBASE)}")
        print(f"file_base=0x{file_base:X} ({file_base:,}) file_count={count}")
        print(f"pck start=0x{PCK:X} pck size={fsize - PCK:,}")

        entries = []
        for i in range(count):
            (plen,) = struct.unpack("<I", f.read(4))
            raw = f.read(plen)
            pad = (4 - plen % 4) % 4
            if pad:
                f.read(pad)
            path = raw.decode("utf-8", "replace")
            ofs, size = struct.unpack("<QQ", f.read(16))
            md5 = f.read(16)
            (eflags,) = struct.unpack("<I", f.read(4))
            entries.append({
                "path": path, "ofs": ofs, "size": size, "md5": md5, "flags": eflags,
            })
        dir_end = f.tell()
        print(f"directory ends at 0x{dir_end:X} (rel 0x{dir_end - PCK:X})")

        enc = sum(1 for e in entries if e["flags"] & FILE_ENCRYPTED)
        rem = sum(1 for e in entries if e["flags"] & FILE_REMOVED)
        print(f"\n{len(entries)} entries, {enc} encrypted, {rem} removed")
        for e in entries[:20]:
            print(f"  {e['ofs']:>12,} {e['size']:>10,} flags={e['flags']} {e['path']}")

        # find where the first file actually lives
        if entries:
            e0 = min(entries, key=lambda x: x["ofs"])
            print(f"\nfirst file: {e0['path']} ofs={e0['ofs']:,} size={e0['size']:,}")
            for cand_name, cand in [("file_base", file_base), ("file_base+pck", file_base + PCK),
                                    ("dir_end", dir_end), ("pck+? ", 0)]:
                if cand:
                    f.seek(cand)
                    head = f.read(16)
                    print(f"  {cand_name}=0x{cand:X}: {head.hex(' ', 4)}")

        # extensions histogram
        from collections import Counter
        c = Counter()
        for e in entries:
            p = e["path"]
            c[p.rsplit(".", 1)[-1].lower() if "." in p else "<none>"] += 1
        print("\nextensions:", c.most_common(30))

        # top-level dirs
        d = Counter()
        for e in entries:
            parts = e["path"].split("/")
            d[parts[0] if len(parts) > 1 else "<root>"] += 1
        print("top-level:", d.most_common(25))

        import json
        with open(r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\entries.json", "w", encoding="utf-8") as out:
            json.dump([{**e, "md5": e["md5"].hex()} for e in entries], out, indent=0)
        print("\nwrote entries.json")


if __name__ == "__main__":
    main()
