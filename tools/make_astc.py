#!/usr/bin/env python3
"""Build the mobile (ASTC) texture overlay for Buckshot Roulette web port.

Apple GPUs (iPhone/iPad) cannot decode S3TC/BC1-3, which is why compressed
textures fail to upload in iOS Safari. This converts every compressed ctex
(DXT1/DXT5/RA_AS_RG) to ASTC:

  * ASTC 8x8 (0.25 B/px) for color/albedo textures  - Image::Format 37
  * ASTC 4x4 (1 B/px)   for normal maps (fmt 34)    - Image::Format 35
    (8x8 would smear normals and flatten the lighting)
  * ASTC 4x4 for the keep-size whitelist (the waiver must stay readable)

Output layout mirrors game_data (overlay under build/assets-astc). Mip chain
follows Godot's rule: levels halve to 1x1, per-level bytes =
ceil(w/block)*ceil(h/block)*16 (block = 8 or 4).
"""
import argparse
import io
import os
import struct
import subprocess
import sys
import tempfile
from multiprocessing import Pool

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import rsrc  # noqa: F401  (kept for parity with the other tools)

SRC = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\game_data"
OUT = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\build\assets-astc"
ASTCENC = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\tools\astcenc\bin\astcenc-avx2.exe"

FMT_DXT1 = 17
FMT_DXT3 = 18
FMT_DXT5 = 19
FMT_DXT5_RA_AS_RG = 34
FMT_ASTC_4x4 = 35
FMT_ASTC_8x8 = 37

KEEP_SIZE = ("release form",)

QUALITY = "-fast"


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
    if fmt == FMT_DXT5_RA_AS_RG:
        arr = np.asarray(im)
        x, y = arr[:, :, 0], arr[:, :, 3]
        im = Image.fromarray(np.stack([x, x, x, y], axis=-1), "RGBA")
    return im, fmt, w, h


def mip_sizes(w, h, block, levels):
    """Godot rule: levels halve to 1x1; per level ceil-padded blocks x 16 bytes."""
    out = []
    W, H = w, h
    for _ in range(levels):
        bw = W + ((block - W % block) % block)
        bh = H + ((block - H % block) % block)
        out.append(bw * bh * 16 // (block * block))
        if W == 1 and H == 1:
            break
        W = max(1, W >> 1)
        H = max(1, H >> 1)
    return out


def encode_level(im, block, tmpdir):
    png = os.path.join(tmpdir, "lvl.png")
    astc = os.path.join(tmpdir, "lvl.astc")
    if os.path.exists(astc):
        os.remove(astc)
    im.save(png, format="PNG")
    rr = subprocess.run(
        [ASTCENC, "-cl", png, astc, f"{block}x{block}", QUALITY],
        capture_output=True)
    if rr.returncode != 0 or not os.path.exists(astc):
        raise RuntimeError("astcenc failed: " + rr.stderr.decode("ascii", "replace")[-300:])
    with open(astc, "rb") as f:
        data = f.read()
    os.remove(png)
    os.remove(astc)
    # astcenc writes a 16-byte ASTC file header; Godot wants raw block data.
    return data[16:]


def convert(args_tuple):
    path, out_path = args_tuple
    blob = open(path, "rb").read()
    if blob[:4] != b"GST2":
        return None
    version = struct.unpack_from("<I", blob, 4)[0]
    width, height = struct.unpack_from("<II", blob, 8)
    df, mip_limit = struct.unpack_from("<II", blob, 16)

    dec = decode_bc(blob)
    if dec is None:
        return None
    im, orig_fmt, w, h = dec

    keep = any(k in os.path.basename(path).lower() for k in KEEP_SIZE)
    is_normal = orig_fmt == FMT_DXT5_RA_AS_RG
    fmt = FMT_ASTC_4x4 if (keep or is_normal) else FMT_ASTC_8x8
    block = 4 if fmt == FMT_ASTC_4x4 else 8

    cap = (1 << 30) if keep else 512
    nw, nh = w, h
    while max(nw, nh) > cap and min(nw, nh) > 1:
        nw, nh = max(1, nw // 2), max(1, nh // 2)
    if (nw, nh) != (w, h):
        im = im.resize((nw, nh), Image.LANCZOS)

    tmpdir = tempfile.mkdtemp(prefix="brastc_")
    try:
        out = bytearray()
        lvl = 0
        sizes = mip_sizes(nw, nh, block, 64)
        cur = im
        while lvl < len(sizes):
            coded = encode_level(cur, block, tmpdir)
            want = sizes[lvl]
            if len(coded) != want:
                raise ValueError(f"astc {len(coded)} != {want} ({nw}x{nh} b{block})")
            out += coded
            lvl += 1
            if nw == 1 and nh == 1:
                break
            nw, nh = max(1, nw >> 1), max(1, nh >> 1)
            cur = cur.resize((nw, nh), Image.LANCZOS)

        new_df = df | (1 << 23) if lvl > 1 else df & ~(1 << 23)
        head = bytearray(52)
        head[0:4] = b"GST2"
        struct.pack_into("<I", head, 4, version)
        struct.pack_into("<II", head, 8, im.width, im.height)
        struct.pack_into("<II", head, 16, new_df, mip_limit)
        struct.pack_into("<IHHII", head, 36, 0, im.width, im.height, lvl - 1, fmt)
        result = bytes(head) + bytes(out)
    finally:
        try:
            os.rmdir(tmpdir)
        except OSError:
            pass
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(result)
    return len(result)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=12)
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
    print(f"encoding {len(tasks)} textures to ASTC ({args.workers} workers)", flush=True)

    done = failed = 0
    total_out = 0
    with Pool(args.workers) as pool:
        for i, res in enumerate(pool.imap_unordered(convert, tasks, chunksize=4)):
            if res is None:
                failed += 1
            else:
                done += 1
                total_out += res
            if (i + 1) % 50 == 0:
                print(f"  {i + 1}/{len(tasks)} done={done} failed={failed} "
                      f"out={total_out / 1e6:.0f}MB", flush=True)
    print(f"ASTC: converted {done}, skipped/failed {failed}, total {total_out / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
