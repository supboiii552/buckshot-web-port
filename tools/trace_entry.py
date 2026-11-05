#!/usr/bin/env python3
"""Trace decoding of one project.binary entry."""
import struct
import sys

sys.path.insert(0, r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\tools")
import dump_project as dp

PATH = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\game_data\project.binary"
TARGET = sys.argv[1] if len(sys.argv) > 1 else "input/ui_accept"

blob = open(PATH, "rb").read()
r = dp.R(blob[8:])
target_val = None
while r.p < len(r.b):
    klen = r.u32()
    key = r.raw(klen).decode()
    vlen = r.u32()
    start = r.p
    if key == TARGET:
        target_val = (start, vlen)
        break
    r.p += vlen

assert target_val, "key not found"
start, vlen = target_val
print(f"{TARGET}: value at {start}, {vlen} bytes")
print("head:", r.b[start:start + 40].hex(" ", 4))

orig = dp.dec
depth_names = {}


def traced(rr, depth=0):
    at = rr.p
    hdr = struct.unpack_from("<I", rr.b, rr.p)[0]
    t = hdr & 0xFF
    try:
        v = orig(rr, depth)
        print(f"{'  ' * depth}@{at:5} type={t:2} -> {str(v)[:70]}")
        return v
    except Exception as e:
        print(f"{'  ' * depth}@{at:5} type={t:2} FAILED {e}")
        raise


dp.dec = traced
r.p = start
try:
    dp.dec(r)
except Exception:
    pass
