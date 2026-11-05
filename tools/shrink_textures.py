#!/usr/bin/env python3
"""Downscale / fix Buckshot Roulette's .ctex textures for the web (WebGL2) port.

.ctex (Godot 4.1) layout:
  0   'GST2'
  4   u32 version (1)
  8   u32 width
  12  u32 height
  16  u32 data_format_flags  (bit23 HAS_MIPMAPS, ...)
  20  u32 mipmap_limit (-1)
  24  u32 reserved[3]
  36  u32 container_format   (0 = raw image data, 1 = png, 2 = webp, 3 = basis)
  40  u16 w, h
  44  u32 mipmap_count (levels - 1)
  48  u32 Image::Format
  52  mip data (level 0 first)

Why textures are touched at all:
  * WebGL2 rejects compressed (S3TC/BPTC) uploads whose base-level width or
    height is not a multiple of 4 (desktop OpenGL tolerates them). The
    original pack has 253 such textures - they fail to upload in the browser
    and render untextured/black. Fix: pad to multiples of 4 (edge replicate)
    and regenerate the mip chain.
  * DXT1 textures may use BC1a (1-bit alpha). Encoding must go through RGBA,
    never RGB, or cutouts are destroyed.
  * Documents the player must read (the waiver) keep their original size.

Textures that need neither downscaling nor padding are copied through
byte-identical: no pointless re-encode, no quality loss.
"""
import argparse
import io
import os
import struct
import sys

import numpy as np
from PIL import Image

FMT_L8 = 0
FMT_RGB8 = 4
FMT_RGBA8 = 5
FMT_DXT1 = 17
FMT_DXT3 = 18
FMT_DXT5 = 19
FMT_DXT5_RA_AS_RG = 34
FMT_BPTC = 24

COMPRESSED = {FMT_DXT1: 8, FMT_DXT3: 16, FMT_DXT5: 16, FMT_DXT5_RA_AS_RG: 16}
RAW_PIXELS = {FMT_L8: (1, 1), FMT_RGB8: (3, 4), FMT_RGBA8: (4, 4)}

# textures that must stay readable at original size (player-facing documents)
KEEP_SIZE = ("release form",)


def dds_header(w, h, fourcc):
    bs = 8 if fourcc == b"DXT1" else 16
    linsize = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * bs
    hdr = bytearray()
    hdr += b"DDS "
    hdr += struct.pack("<7I", 124, 0x1 | 0x2 | 0x4 | 0x1000 | 0x80000, h, w, linsize, 0, 0)
    hdr += struct.pack("<11I", *([0] * 11))
    hdr += struct.pack("<4I", 32, 0x4, int.from_bytes(fourcc, "little"), 0)
    hdr += struct.pack("<4I", 0, 0, 0, 0)
    hdr += struct.pack("<5I", 0x1000, 0, 0, 0, 0)
    assert len(hdr) == 128, len(hdr)
    return bytes(hdr)


def decode_bc(data, w, h, fmt):
    fourcc = b"DXT1" if fmt == FMT_DXT1 else b"DXT5"
    need = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * (8 if fmt == FMT_DXT1 else 16)
    blob = dds_header(w, h, fourcc) + bytes(data[:need])
    im = Image.open(io.BytesIO(blob))
    im.load()
    return im.convert("RGBA")  # Pillow 12 decodes BC1a alpha correctly


def encode_bc(im, fmt):
    """Encode an RGBA image to raw BC1/BC3 blocks (no container header)."""
    src = im.convert("RGBA")
    pf = "DXT1" if fmt == FMT_DXT1 else "DXT5"
    buf = io.BytesIO()
    src.save(buf, format="DDS", pixel_format=pf)
    return buf.getvalue()[128:]


def mip_sizes(w, h, fmt, levels):
    """Byte size of each mip level, matching Image::_get_dst_image_size."""
    out = []
    W, H = w, h
    for _ in range(levels):
        if fmt in COMPRESSED:
            bw = W + ((4 - W % 4) % 4)
            bh = H + ((4 - H % 4) % 4)
            out.append(bw * bh * COMPRESSED[fmt] // 16)
        else:
            bpp, _ = RAW_PIXELS[fmt]
            out.append(W * H * bpp)
        if W == 1 and H == 1:
            break
        W = max(1, W >> 1)
        H = max(1, H >> 1)
    return out


def pad4(im):
    """Pad to a multiple of 4 (BC blocks) by edge replication."""
    w, h = im.size
    nw, nh = (w + 3) // 4 * 4, (h + 3) // 4 * 4
    if (nw, nh) == (w, h):
        return im
    out = Image.new(im.mode, (nw, nh))
    out.paste(im, (0, 0))
    if nw != w:
        out.paste(im.crop((w - 1, 0, w, h)), (w, 0))
    if nh != h:
        out.paste(out.crop((0, h - 1, nw, h)), (0, h))
    return out


def shrink(path, cap):
    """Return new ctex bytes, or None to copy the file through unchanged."""
    with open(path, "rb") as f:
        blob = f.read()
    if blob[:4] != b"GST2":
        return None
    version = struct.unpack_from("<I", blob, 4)[0]
    width, height = struct.unpack_from("<II", blob, 8)
    df, mip_limit = struct.unpack_from("<II", blob, 16)
    container, cw, ch, mips, fmt = struct.unpack_from("<IHHII", blob, 36)
    body = blob[52:]

    if container != 0:
        return None  # webp/png container: uncompressed at upload, leave alone
    if fmt == FMT_BPTC:
        if width % 4 or height % 4:
            print(f"  !! BPTC texture {width}x{height} not mult-4 - needs manual fix")
        return None  # cannot re-encode BPTC here
    if fmt not in COMPRESSED:
        return None

    keep = any(k in os.path.basename(path).lower() for k in KEEP_SIZE)
    eff_cap = 1 << 30 if keep else cap
    need_downscale = max(width, height) > eff_cap
    need_pad = (width % 4) or (height % 4)
    if not need_downscale and not need_pad:
        return None  # legal in WebGL2 and small enough: copy through

    im = decode_bc(body, width, height, fmt)
    if fmt == FMT_DXT5_RA_AS_RG:
        # Normal map stored as X in R, Y in A. Rebuild as (X,X,X,Y).
        arr = np.asarray(im)
        x = arr[:, :, 0]
        y = arr[:, :, 3]
        arr = np.stack([x, x, x, y], axis=-1)
        im = Image.fromarray(arr, "RGBA")

    nw, nh = width, height
    while max(nw, nh) > eff_cap and min(nw, nh) > 1:
        nw = max(1, nw // 2)
        nh = max(1, nh // 2)
    if need_downscale:
        im = im.resize((nw, nh), Image.LANCZOS)

    # WebGL2: base level must be a multiple of 4
    nw, nh = (nw + 3) // 4 * 4, (nh + 3) // 4 * 4
    im = pad4(im)

    sizes = mip_sizes(nw, nh, fmt, 64)
    out = bytearray()
    lvl = 0
    cur = im
    while lvl < len(sizes):
        coded = encode_bc(pad4(cur), fmt)
        want = sizes[lvl]
        if len(coded) != want:
            raise ValueError(f"encoded {len(coded)} bytes, expected {want} "
                             f"({nw}x{nh} fmt{fmt})")
        out += coded
        lvl += 1
        if nw == 1 and nh == 1:
            break
        nw = max(1, nw >> 1)
        nh = max(1, nh >> 1)
        cur = cur.resize((nw, nh), Image.LANCZOS)

    new_df = df | (1 << 23) if lvl > 1 else df & ~(1 << 23)

    head = bytearray(52)
    head[0:4] = b"GST2"
    struct.pack_into("<I", head, 4, version)
    struct.pack_into("<II", head, 8, im.width, im.height)
    struct.pack_into("<II", head, 16, new_df, mip_limit)
    struct.pack_into("<IHHII", head, 36, 0, im.width, im.height, lvl - 1, fmt)
    return bytes(head) + bytes(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--cap", type=int, default=1024)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    paths = []
    for dp, dn, fn in os.walk(args.src):
        for n in fn:
            if n.endswith(".ctex"):
                paths.append(os.path.join(dp, n))
    paths.sort(key=os.path.getsize, reverse=True)
    if args.limit:
        paths = paths[: args.limit]

    before = after = 0
    done = copied = 0
    for i, p in enumerate(paths):
        rel = os.path.relpath(p, args.src)
        try:
            new = shrink(p, args.cap)
        except Exception as e:
            print(f"  FAIL {rel}: {e}")
            continue
        if new is None:
            copied += 1
            continue
        dst = os.path.join(args.out, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        with open(dst, "wb") as f:
            f.write(new)
        before += os.path.getsize(p)
        after += len(new)
        done += 1
        if done % 50 == 0:
            print(f"  {done} {before/1e6:.0f} -> {after/1e6:.0f} MB", flush=True)
    print(f"rewrote {done} textures: {before/1e6:.1f} -> {after/1e6:.1f} MB "
          f"({after/max(before,1)*100:.0f}%); {copied} copied through unchanged")


if __name__ == "__main__":
    sys.exit(main())
