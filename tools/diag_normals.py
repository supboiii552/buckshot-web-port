#!/usr/bin/env python3
"""Compare only the channels the engine actually reads in fmt34 (RA_AS_RG):
X = R, Y = A. Also report the length distribution of reconstructed normals."""
import io
import os
import struct
import random

import numpy as np
from PIL import Image

ORIG = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\game_data\.godot\imported"
SHRK = os.path.join(r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\build\assets", ".godot", "imported")


def dds_hdr(w, h, fourcc):
    bs = 8 if fourcc == b"DXT1" else 16
    ls = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * bs
    hdr = bytearray()
    hdr += b"DDS "
    hdr += struct.pack("<7I", 124, 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000, h, w, ls, 0, 0)
    hdr += struct.pack("<11I", *([0] * 11))
    hdr += struct.pack("<4I", 32, 0x4, int.from_bytes(fourcc, "little"), 0)
    hdr += struct.pack("<4I", 0, 0, 0, 0)
    hdr += struct.pack("<5I", 0x1000, 0, 0, 0, 0)
    return bytes(hdr)


def decode(path):
    blob = open(path, "rb").read()
    w, h = struct.unpack_from("<II", blob, 8)
    cont, cw, ch, mips, fmt = struct.unpack_from("<IHHII", blob, 36)
    need = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * 16
    img = Image.open(io.BytesIO(dds_hdr(w, h, b"DXT5") + blob[52:52 + need]))
    img.load()
    return np.asarray(img.convert("RGBA")), (w, h)


files = [f for f in os.listdir(ORIG) if f.endswith(".ctex")]
random.seed(3)
# collect fmt34 files that also exist shrunk
f34 = []
for f in files:
    blob = open(os.path.join(ORIG, f), "rb").read()
    if blob[:4] != b"GST2":
        continue
    cont, cw, ch, mips, fmt = struct.unpack_from("<IHHII", blob, 36)
    if cont == 0 and fmt == 34 and os.path.exists(os.path.join(SHRK, f)):
        f34.append(f)
sample = random.sample(f34, min(12, len(f34)))
print(f"fmt34 originals with shrunk copy: {len(f34)}; sampling {len(sample)}\n")
for f in sample:
    o, (w, h) = decode(os.path.join(ORIG, f))
    s, (w2, h2) = decode(os.path.join(SHRK, f))
    if (w2, h2) != (w, h):
        s = np.asarray(Image.fromarray(s).resize((w, h), Image.BILINEAR))
    er = np.abs(o[:, :, 0].astype(np.int16) - s[:, :, 0].astype(np.int16)).mean()
    ea = np.abs(o[:, :, 3].astype(np.int16) - s[:, :, 3].astype(np.int16)).mean()
    # reconstructed normal length for the SHRUNK map: x,y in [0,1] -> [-1,1]
    x = s[:, :, 0].astype(np.float32) / 127.5 - 1.0
    y = s[:, :, 3].astype(np.float32) / 127.5 - 1.0
    z = np.sqrt(np.maximum(0.0, 1.0 - x * x - y * y))
    nlen = np.sqrt(x * x + y * y + z * z)
    xo = o[:, :, 0].astype(np.float32) / 127.5 - 1.0
    yo = o[:, :, 3].astype(np.float32) / 127.5 - 1.0
    zo = np.sqrt(np.maximum(0.0, 1.0 - xo * xo - yo * yo))
    nlen_o = np.sqrt(xo * xo + yo * yo + zo * zo)
    print(f"{f[:58]}\n   {w}x{h}->{w2}x{h2}  errR={er:.2f} errA={ea:.2f}  "
          f"|n| orig mean {nlen_o.mean():.3f}  shrunk mean {nlen.mean():.3f}")
