#!/usr/bin/env python3
"""Find the REAL active environment: main.scn's external resource table +
any Environment-typed exported .res files."""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rsrc

ROOT = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\game_data\.godot\exported\133200997"
SCN = os.path.join(ROOT, "export-3ad5c15c4f3250da0cc7c1af1770d85f-main.scn")

blob = open(SCN, "rb").read()
r = rsrc.Reader(blob)
r.p = 4
res = rsrc.Resource()
r.u32(); r.u32(); r.u32(); r.u32(); r.u32()
res.class_name = r.ustr()
res.import_md = r.u64()
res.format_flags = r.u32()
res.uid = r.u64()
if res.format_flags & 8:
    res.script_class = r.ustr()
r.raw(4 * 11)
n = r.u32()
res.strings = [r.ustr() for _ in range(n)]
n = r.u32()
print("external resources of main.scn:")
for _ in range(n):
    cls = r.ustr()
    p = r.ustr()
    uid = r.u64()
    print(f"   {cls:24s} {p}")
