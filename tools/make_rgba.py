#!/usr/bin/env python3
"""Build the fallback (uncompressed) texture overlay for Buckshot Roulette.

pck-rgba is served only when the loader's compressed-texture upload test
fails on a device: plain RGBA8/RGB8/RG8 need no WebGL extension, no engine
format gate and no software decode, so they render on every WebGL2 device.

Mapping:
  * opaque DXT1/DXT3/DXT5 color  -> FORMAT_RGB8  (3 B/px)
  * alpha color textures         -> FORMAT_RGBA8 (4 B/px)
  * DXT5_RA_AS_RG normal maps    -> FORMAT_RG8   (2 B/px, R=x G=y)
  * keep-size whitelist (waiver) -> no downscale

Output layout mirrors game_data (overlay under build/assets-rgba). Mip chain
halves to 1x1 like Godot's rule.
"""
import argparse
import io
import os
import struct
import sys
from multiprocessing import Pool

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SRC = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\game_data"
OUT = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\build\assets-rgba"

FMT_DXT1 = 17
FMT_DXT3 = 18
FMT_DXT5 = 19
FMT_DXT5_RA_AS_RG = 34
FMT_RGB8 = 4
FMT_RGBA8 = 5
FMT_RG8 = 3

KEEP_SIZE = ("release form",)
CAP = 256


def dds_header(w, h, fourcc):
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


def decode_bc(blob):
    w, h = struct.unpack_from("<II", blob, 8)
    cont, cw, ch, mips, fmt = struct.unpack_from("<IHHII", blob, 36)
    if cont != 0 or fmt not in (FMT_DXT1, FMT_DXT3, FMT_DXT5, FMT_DXT5_RA_AS_RG):
        return None
    fourcc = b"DXT1" if fmt == FMT_DXT1 else b"DXT5"
    need = max(1, (w + 3) // 4) * max(1, (h + 3) // 4) * (8 if fmt == FMT_DXT1 else 16)
    img = Image.open(io.BytesIO(dds_header(w, h, fourcc) + blob[52:52 + need]))
    img.load()
    im = img.convert("RGBA")
    return im, fmt, w, h


def mip_chain(arr, out):
    """Append the halving mip chain of an HxWx4 array as raw bytes."""
    cur = arr
    while True:
        out += cur.tobytes()
        if cur.shape[0] == 1 and cur.shape[1] == 1:
            break
        h = max(1, cur.shape[0] >> 1)
        w = max(1, cur.shape[1] >> 1)
        cur = np.asarray(Image.fromarray(cur).resize((w, h), Image.LANCZOS))
    return out


def convert(args_tuple):
    path, out_path = args_tuple
    blob = open(path, "rb").read()
    if blob[:4] != b"GST2":
        return None
    version = struct.unpack_from("<I", blob, 4)[0]
    df, mip_limit = struct.unpack_from("<II", blob, 16)

    dec = decode_bc(blob)
    if dec is None:
        return None
    im, orig_fmt, w, h = dec

    keep = any(k in os.path.basename(path).lower() for k in KEEP_SIZE)
    is_normal = orig_fmt == FMT_DXT5_RA_AS_RG

    arr = np.asarray(im)
    if is_normal:
        x, y = arr[:, :, 0], arr[:, :, 3]
        arr = np.stack([x, y], axis=-1)  # RG8
        out_fmt = FMT_RG8
    else:
        has_alpha = arr[:, :, 3].min() < 255
        out_fmt = FMT_RGBA8 if (has_alpha or keep) else FMT_RGB8
        if out_fmt == FMT_RGB8:
            arr = arr[:, :, :3]

    cap = (1 << 30) if keep else CAP
    nw, nh = w, h
    while max(nw, nh) > cap and min(nw, nh) > 1:
        nw, nh = max(1, nw // 2), max(1, nh // 2)
    if (nw, nh) != (w, h):
        arr = np.asarray(Image.fromarray(arr).resize((nw, nh), Image.LANCZOS))

    data = mip_chain(arr, bytearray())
    lvl = 0
    W, H = nw, nh
    while True:
        lvl += 1
        if W == 1 and H == 1:
            break
        W, H = max(1, W >> 1), max(1, H >> 1)

    new_df = df | (1 << 23) if lvl > 1 else df & ~(1 << 23)
    head = bytearray(52)
    head[0:4] = b"GST2"
    struct.pack_into("<I", head, 4, version)
    struct.pack_into("<II", head, 8, nw, nh)
    struct.pack_into("<II", head, 16, new_df, mip_limit)
    struct.pack_into("<IHHII", head, 36, 0, nw, nh, lvl - 1, out_fmt)
    result = bytes(head) + bytes(data)

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(result)
    return len(result)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()

    imp = os.path.join(SRC, ".godot", "imported")
    tasks = []
    for f in sorted(os.listdir(imp)):
        if not f.endswith(".ctex"):
            continue
        blob_head = open(os.path.join(imp, f), "rb").read(52)
        if blob_head[:4] != b"GST2":
            continue
        cont = struct.unpack_from("<I", blob_head, 36)[0]
        fmt = struct.unpack_from("<I", blob_head, 48)[0]
        if cont != 0 or fmt not in (FMT_DXT1, FMT_DXT3, FMT_DXT5, FMT_DXT5_RA_AS_RG):
            continue
        rel = os.path.join(".godot", "imported", f)
        tasks.append((os.path.join(imp, f), os.path.join(OUT, rel)))
    if args.limit:
        tasks = tasks[: args.limit]
    print(f"encoding {len(tasks)} textures to uncompressed RGBA ({args.workers} workers)", flush=True)

    done = failed = 0
    total_out = 0
    with Pool(args.workers) as pool:
        for i, res in enumerate(pool.imap_unordered(convert, tasks, chunksize=4)):
            if res is None:
                failed += 1
            else:
                done += 1
                total_out += res
            if (i + 1) % 100 == 0:
                print(f"  {i + 1}/{len(tasks)} done={done} failed={failed} "
                      f"out={total_out / 1e6:.0f}MB", flush=True)
    print(f"RGBA: converted {done}, skipped/failed {failed}, total {total_out / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
