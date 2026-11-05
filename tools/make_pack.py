#!/usr/bin/env python3
"""Copy the embedded PCK out of the Buckshot Roulette exe into godot.pck.

The embedded pack stores `file_base` as an absolute offset inside the exe.
Godot computes `ofs = file_base + entry_offset + pack_start_offset`, so for a
standalone pack we rewrite file_base to the pack-relative value.
"""
import struct
import sys

EXE = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\Buckshot Roulette.exe"
PCK_START = 0x03725E00
OUT = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\web\godot.pck"

FREE_HEADER_OFF = 20  # pack_flags u32
FILE_BASE_OFF = 24  # file_base u64


def main():
    import os

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(EXE, "rb") as f:
        f.seek(0, 2)
        size = f.tell()
        f.seek(PCK_START)
        hdr = bytearray(f.read(100))
        assert hdr[:4] == b"GDPC", hdr[:4]

        pack_flags = struct.unpack_from("<I", hdr, FREE_HEADER_OFF)[0]
        file_base = struct.unpack_from("<Q", hdr, FILE_BASE_OFF)[0]
        rel_base = file_base - PCK_START
        print(f"embedded: flags=0x{pack_flags:X} file_base=0x{file_base:X} -> rel 0x{rel_base:X}")
        assert rel_base >= 100, rel_base

        struct.pack_into("<Q", hdr, FILE_BASE_OFF, rel_base)

        f.seek(PCK_START)
        remaining = size - PCK_START
        with open(OUT, "wb") as out:
            out.write(hdr)
            left = remaining - len(hdr)
            while left > 0:
                chunk = f.read(min(left, 8 << 20))
                if not chunk:
                    break
                out.write(chunk)
                left -= len(chunk)
    print(f"wrote {OUT} ({size - PCK_START:,} bytes)")


if __name__ == "__main__":
    main()
