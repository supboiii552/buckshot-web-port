#!/usr/bin/env python3
"""Inspect .ctex (GST2) and .scn (RSRC) headers, list size distribution."""
import glob
import os
import struct
from collections import Counter

ROOT = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\game_data"

print("=== biggest .ctex ===")
ctex = sorted(glob.glob(os.path.join(ROOT, "**", "*.ctex"), recursive=True),
              key=os.path.getsize, reverse=True)
fmt_hist = Counter()
for p in ctex:
    with open(p, "rb") as f:
        b = f.read(64)
    magic = b[:4]
    if magic == b"GST2":
        w, h, mip, fmt = struct.unpack_from("<IIII", b, 4)
        fmt_hist[fmt] += 1
for p in ctex[:6]:
    with open(p, "rb") as f:
        b = f.read(64)
    w, h, mip, fmt = struct.unpack_from("<IIII", b, 4)
    print(f"  {os.path.basename(p)[:60]:62} {os.path.getsize(p)/1e6:6.2f}MB "
          f"magic={b[:4]!r} w={w} h={h} mip={mip} fmt={fmt} hdr={b[:40].hex(' ',4)}")

print("\nctex format histogram (format id -> count):", dict(fmt_hist))
print("ctex total:", sum(os.path.getsize(p) for p in ctex) / 1e6, "MB,", len(ctex), "files")

print("\n=== biggest .scn ===")
scn = sorted(glob.glob(os.path.join(ROOT, "**", "*.scn"), recursive=True),
             key=os.path.getsize, reverse=True)
for p in scn[:6]:
    with open(p, "rb") as f:
        b = f.read(40)
    print(f"  {os.path.basename(p)[:60]:62} {os.path.getsize(p)/1e6:6.2f}MB {b.hex(' ',4)}")

print("\n=== biggest ogg ===")
ogg = sorted(glob.glob(os.path.join(ROOT, "**", "*.oggvorbisstr"), recursive=True),
             key=os.path.getsize, reverse=True)
for p in ogg[:4]:
    with open(p, "rb") as f:
        b = f.read(40)
    print(f"  {os.path.basename(p)[:60]:62} {os.path.getsize(p)/1e6:6.2f}MB {b.hex(' ',4)}")
print("ogg total:", sum(os.path.getsize(p) for p in ogg) / 1e6, "MB")
