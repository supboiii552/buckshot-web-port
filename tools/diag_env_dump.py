#!/usr/bin/env python3
"""Dump Environment properties from exported scenes (surgical: header +
string table + per-resource bodies only for Environment-typed resources)."""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rsrc

EXP = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\game_data\.godot\exported\133200997"
TARGETS = sys.argv[1:] or [
    "export-3ad5c15c4f3250da0cc7c1af1770d85f-main.scn",
    "export-1ce5c86e8ca186dcaaeaa8726f1268db-menu.scn",
    "export-7df7c9f633960c6d5c53f69d7666ddec-heaven.scn",
]


def scan_envs(path):
    blob = open(path, "rb").read()
    r = rsrc.Reader(blob)
    r.p = 4
    res = rsrc.Resource()
    res.big_endian = r.u32()
    res.use_real64 = r.u32()
    r.u32(); r.u32(); r.u32()
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
    for _ in range(n):
        r.ustr(); r.ustr(); r.u64()
    n = r.u32()
    internals = []
    for _ in range(n):
        p = r.ustr()
        ofs = r.u64()
        internals.append((p, ofs))

    out = []
    for path_i, ofs in internals:
        r.p = ofs
        try:
            type_name = r.ustr()
            if type_name != "Environment":
                continue
            nprops = r.u32()
            props = []
            for _ in range(nprops):
                idx = r.u32()
                name = res.strings[idx] if idx < len(res.strings) else f"#{idx}"
                props.append((name, rsrc.read_variant(r, res)))
            out.append((path_i, props))
        except Exception as e:
            out.append((path_i, [("PARSE_ERROR", str(e))]))
    return out


for t in TARGETS:
    p = os.path.join(EXP, t)
    envs = scan_envs(p)
    print(f"\n=== {t}: {len(envs)} Environment resources")
    for path_i, props in envs:
        interesting = [(k, v) for k, v in props if any(
            s in k for s in ("tonemap", "adjustment", "glow_enabled", "ambient_light",
                             "bg_mode", "bg_energy", "fog_enabled", "fog_light_color",
                             "fog_density", "volumetric"))]
        if interesting:
            print(f"  {path_i}")
            for k, v in interesting:
                print(f"      {k} = {v}")
