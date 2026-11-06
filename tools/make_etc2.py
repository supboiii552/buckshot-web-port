#!/usr/bin/env python3
"""Build the mobile (ETC2) texture overlay for Buckshot Roulette web port.

Why ETC2 and not ASTC: Godot 4.1.4's GLES3 config hardcodes etc2_supported =
true on GLES/web, but astc_supported only checks GL-style extension names
(GL_KHR_texture_compression_astc_ldr ...) which Safari's WebGL2 never reports
(it reports WEBGL_compressed_texture_astc). So the engine always refuses ASTC
on the web runtime (and 4.1 has no software ASTC decoder) -> white objects.
ETC2 is accepted by Safari iOS 13.4+ (WEBGL_compressed_texture_etc) and is
uploaded natively by the engine with no extension gate.

Mapping (source desktop formats -> ETC2):
  * DXT1 color, opaque            -> ETC2_RGB8   (0.5 B/px)
  * DXT1/DXT3/DXT5 with alpha     -> ETC2_RGBA8  (1 B/px)
  * DXT5_RA_AS_RG normal maps     -> ETC2_RG11   (1 B/px, R=x G=y)
  * keep-size whitelist (waiver)  -> ETC2_RGBA8, no downscale

Output layout mirrors game_data (overlay under build/assets-etc2). Mip chain
follows Godot's rule: levels halve to 1x1, per level
ceil(w/4)*ceil(h/4)*blockbytes (RGB8=8, RGBA8=16, RG11=16).
"""
import argparse
import os
import struct
import sys
from multiprocessing import Pool

import numpy as np
import etcpak
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SRC = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\game_data"
OUT = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\build\assets-etc2"

FMT_DXT1 = 17
FMT_DXT3 = 18
FMT_DXT5 = 19
FMT_DXT5_RA_AS_RG = 34
FMT_ETC2_RGB8 = 30
FMT_ETC2_RGBA8 = 31
FMT_ETC2_RG11 = 28

KEEP_SIZE = ("release form",)
CAP = 384


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
    img = Image.open(io_bytes(dds_header(w, h, fourcc) + blob[52:52 + need]))
    img.load()
    im = img.convert("RGBA")
    return im, fmt, w, h


def io_bytes(b):
    import io
    return io.BytesIO(b)


def mip_bytes(w, h, blockbytes):
    """Total mip-chain bytes for an ETC2 texture (4x4 blocks)."""
    out = 0
    W, H = w, h
    while True:
        out += ((W + 3) // 4) * ((H + 3) // 4) * blockbytes
        if W == 1 and H == 1:
            break
        W = max(1, W >> 1)
        H = max(1, H >> 1)
    return out


def encode_chain(im, enc, blockbytes):
    """Encode the full mip chain; returns (data, level_count).

    etcpak rejects non-mult-4 sizes, so every level is edge-padded up to a
    multiple of 4 first; the block count is unchanged (ceil of the true dims),
    and ETC2 accepts odd dims at upload time.
    """
    out = bytearray()
    lvl = 0
    cur = im
    while True:
        pw = (cur.width + 3) // 4 * 4
        ph = (cur.height + 3) // 4 * 4
        if (pw, ph) != (cur.width, cur.height):
            arr = np.asarray(cur)
            arr = np.pad(arr, ((0, ph - cur.height), (0, pw - cur.width), (0, 0)), mode="edge")
            raw = arr.tobytes()
        else:
            raw = cur.tobytes()
        coded = enc(raw, pw, ph)
        want = ((cur.width + 3) // 4) * ((cur.height + 3) // 4) * blockbytes
        if len(coded) != want:
            raise ValueError(f"etc2 {len(coded)} != {want} ({cur.width}x{cur.height})")
        out += coded
        lvl += 1
        if cur.width == 1 and cur.height == 1:
            break
        cur = cur.resize((max(1, cur.width >> 1), max(1, cur.height >> 1)), Image.LANCZOS)
    return bytes(out), lvl


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

    if is_normal:
        arr = np.asarray(im)
        x, y = arr[:, :, 0], arr[:, :, 3]
        enc_im = Image.fromarray(np.stack([x, y, np.zeros_like(x), np.ones_like(x) * 255], axis=-1), "RGBA")
        enc = etcpak.compress_eac_rg
        blockbytes = 16
        out_fmt = FMT_ETC2_RG11
        cap = (1 << 30)
    else:
        enc_im = im
        has_alpha = im.getchannel("A").getextrema()[0] < 255
        if has_alpha or keep:
            enc = etcpak.compress_etc2_rgba
            blockbytes = 16
            out_fmt = FMT_ETC2_RGBA8
        else:
            enc = etcpak.compress_etc2_rgb
            blockbytes = 8
            out_fmt = FMT_ETC2_RGB8
        cap = (1 << 30) if keep else CAP

    nw, nh = w, h
    while max(nw, nh) > cap and min(nw, nh) > 1:
        nw, nh = max(1, nw // 2), max(1, nh // 2)
    if (nw, nh) != (w, h):
        enc_im = enc_im.resize((nw, nh), Image.LANCZOS)

    data, lvl = encode_chain(enc_im, enc, blockbytes)

    new_df = df | (1 << 23) if lvl > 1 else df & ~(1 << 23)
    head = bytearray(52)
    head[0:4] = b"GST2"
    struct.pack_into("<I", head, 4, version)
    struct.pack_into("<II", head, 8, enc_im.width, enc_im.height)
    struct.pack_into("<II", head, 16, new_df, mip_limit)
    struct.pack_into("<IHHII", head, 36, 0, enc_im.width, enc_im.height, lvl - 1, out_fmt)
    result = bytes(head) + data

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
    print(f"encoding {len(tasks)} textures to ETC2 ({args.workers} workers)", flush=True)

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
    print(f"ETC2: converted {done}, skipped/failed {failed}, total {total_out / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
