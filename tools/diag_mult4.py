#!/usr/bin/env python3
"""Count compressed ctex whose base dimensions are not multiples of 4
(illegal in WebGL2 -> texture upload fails -> untextured/black objects)."""
import os
import struct

ORIG = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\game_data\.godot\imported"
SHRK = os.path.join(r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\build\assets", ".godot", "imported")

bad = []
ok = 0
for f in sorted(os.listdir(ORIG)):
    if not f.endswith(".ctex"):
        continue
    blob = open(os.path.join(ORIG, f), "rb").read()
    if blob[:4] != b"GST2":
        continue
    w, h = struct.unpack_from("<II", blob, 8)
    cont, cw, ch, mips, fmt = struct.unpack_from("<IHHII", blob, 36)
    if cont != 0 or fmt not in (17, 18, 19, 24, 34):
        continue
    if w % 4 or h % 4:
        sz = os.path.getsize(os.path.join(ORIG, f))
        shrunk = os.path.exists(os.path.join(SHRK, f))
        bad.append((f, fmt, w, h, sz, shrunk))
    else:
        ok += 1

print(f"compressed ctex mult-4 OK: {ok}, INVALID (WebGL2 rejects): {len(bad)}")
tot = sum(b[4] for b in bad)
print(f"their total size: {tot/1e6:.1f} MB; shrunk-overlay present for {sum(1 for b in bad if b[5])}")
for f, fmt, w, h, sz, shrunk in bad[:40]:
    print(f"  fmt{fmt:<3} {w:>5}x{h:<5} {sz/1024:>7.0f}KB  shrunk={shrunk}  {f[:60]}")
