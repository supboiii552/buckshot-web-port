#!/usr/bin/env python3
"""Diagnose the texture shrinker, round 2.

1. Pillow DXT5 alpha-block roundtrip fidelity (normal maps live in R+A).
2. Scan original DXT1 ctex for BC1a usage (1-bit alpha) - Pillow decodes DXT1
   as RGB and the tool converts to RGB, so any alpha there is destroyed.
3. Original vs shrunk comparison for the user-flagged textures.
"""
import io
import os
import struct

import numpy as np
from PIL import Image

ORIG = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\game_data\.godot\imported"
SHRK = os.path.join(r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\build\assets", ".godot", "imported")
OUTD = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\diag"
os.makedirs(OUTD, exist_ok=True)


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


# --- 1. Pillow DXT5 alpha roundtrip ------------------------------------------
rng = np.random.default_rng(7)
test = np.zeros((64, 64, 4), np.uint8)
test[:, :, :3] = rng.integers(0, 256, (64, 64, 3))
test[:, :, 3] = np.clip((np.sin(np.linspace(0, 7, 64)) * 100 + 128), 0, 255).astype(np.uint8)[:, None]
buf = io.BytesIO()
Image.fromarray(test, "RGBA").save(buf, format="DDS", pixel_format="DXT5")
dec = np.asarray(Image.open(io.BytesIO(buf.getvalue())).convert("RGBA"))
err = np.abs(dec[:, :, 3].astype(np.int16) - test[:, :, 3].astype(np.int16))
print(f"Pillow DXT5 alpha roundtrip: mean err {err.mean():.2f}, max {err.max()}, "
      f"px>32 off: {(err > 32).sum()}/{err.size}")

# same for DXT1 color (no alpha input)
buf = io.BytesIO()
Image.fromarray(test[:, :, :3], "RGB").save(buf, format="DDS", pixel_format="DXT1")
dec1 = np.asarray(Image.open(io.BytesIO(buf.getvalue())).convert("RGB"))
err1 = np.abs(dec1.astype(np.int16) - test[:, :, :3].astype(np.int16)).mean()
print(f"Pillow DXT1 color roundtrip: mean err {err1:.2f}")


# --- 2. BC1a scan of original DXT1 textures -----------------------------------
def scan_bc1a(blob, w, h):
    """Detect 3-color (punchthrough/alpha) blocks in raw BC1 data."""
    bw, bh = (w + 3) // 4, (h + 3) // 4
    data = blob[52:52 + bw * bh * 8]
    blocks = np.frombuffer(data[:len(data) // 8 * 8], dtype=np.uint16).reshape(-1, 4)
    c0, c1 = blocks[:, 0].astype(np.uint32), blocks[:, 1].astype(np.uint32)
    return (c0 <= c1).sum(), len(blocks)


total_blocks = punch = 0
with_alpha = []
for f in sorted(os.listdir(ORIG)):
    if not f.endswith(".ctex"):
        continue
    blob = open(os.path.join(ORIG, f), "rb").read()
    if blob[:4] != b"GST2":
        continue
    w, h = struct.unpack_from("<II", blob, 8)
    cont, cw, ch, mips, fmt = struct.unpack_from("<IHHII", blob, 36)
    if cont != 0 or fmt != 17:
        continue
    p, n = scan_bc1a(blob, w, h)
    total_blocks += n
    punch += p
    if p:
        with_alpha.append((f, p, n))
print(f"\nBC1a scan: {punch}/{total_blocks} blocks use 3-color alpha mode "
      f"across DXT1 textures; textures with punchthrough blocks: {len(with_alpha)}")
for f, p, n in with_alpha[:12]:
    print(f"   {f[:70]}  {p}/{n} blocks")


# --- 3. flagged textures: original vs shrunk ----------------------------------
def decode(path):
    blob = open(path, "rb").read()
    if blob[:4] != b"GST2":
        return None
    w, h = struct.unpack_from("<II", blob, 8)
    cont, cw, ch, mips, fmt = struct.unpack_from("<IHHII", blob, 36)
    body = blob[52:]
    if fmt == 17:
        fourcc, bs = b"DXT1", 8
    elif fmt in (19, 34):
        fourcc, bs = b"DXT5", 16
    else:
        return ("unhandled", fmt)
    need = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * bs
    img = Image.open(io.BytesIO(dds_hdr(w, h, fourcc) + body[:need]))
    img.load()
    return np.asarray(img.convert("RGBA")), fmt, (w, h)


targets = ["release form", "defib charge png", "defib charge_excl", "health counter main1",
           "dealer hands main1_health counter metal", "health counter corruption",
           "waiver", "contract", "sign"]
seen = set()
for f in sorted(os.listdir(ORIG)):
    if not f.endswith(".ctex"):
        continue
    low = f.lower()
    if not any(t in low for t in targets) or f in seen:
        continue
    seen.add(f)
    r = decode(os.path.join(ORIG, f))
    if r is None or (isinstance(r[0], str)):
        print(f"{f[:60]}: {r}")
        continue
    orig, fmt, (w, h) = r
    tag = "NOT SHRUNK (missing from assets)"
    sp = os.path.join(SHRK, f)
    if os.path.exists(sp):
        r2 = decode(sp)
        if r2 is None or (isinstance(r2[0], str)):
            tag = f"shrunk decode failed: {r2}"
        else:
            shr, fmt2, (w2, h2) = r2
            shr_big = shr if (w2, h2) == (w, h) else np.asarray(
                Image.fromarray(shr).resize((w, h), Image.BILINEAR))
            diff = np.abs(orig.astype(np.int16) - shr_big.astype(np.int16)).mean()
            a2 = shr_big[:, :, 3]
            tag = (f"shrunk {w2}x{h2} fmt{fmt2} mean|diff|={diff:.1f} "
                   f"alpha<128 orig={(orig[:, :, 3] < 128).sum()} shrunk={(a2 < 128).sum()}")
            Image.fromarray(shr).save(os.path.join(OUTD, "shr_" + f[:40].replace(" ", "_") + ".png"))
    a = orig[:, :, 3]
    print(f"{f[:64]}\n    orig fmt{fmt} {w}x{h} alpha<128={(a < 128).sum()}  |  {tag}")
    Image.fromarray(orig).save(os.path.join(OUTD, "orig_" + f[:40].replace(" ", "_") + ".png"))
