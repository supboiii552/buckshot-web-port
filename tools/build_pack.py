#!/usr/bin/env python3
"""Build a stock Godot 4.x (pack format 2) PCK from an extracted directory.

Format 2 layout (Godot 4.0 - 4.2):
  header (100 bytes):
    'GDPC', u32 format=2, u32 ver_major, u32 ver_minor, u32 ver_patch,
    u32 pack_flags=0, u64 file_base, u32 reserved[16], u32 file_count
  per entry:
    u32 path_len (path bytes + NUL padding, 4-aligned)
    path bytes (utf-8) + pad NULs
    u64 offset (relative to file_base), u64 size, u8 md5[16], u32 flags

The loader computes: ofs = file_base + entry_offset + pack_start_offset,
so for a standalone .pck file_base is relative to the pack and must point
past the directory.
"""
import argparse
import hashlib
import os
import struct
import sys

PACK_FORMAT = 2
VER = (4, 1, 1)
HEADER_SIZE = 100


def pad4(n):
    return (4 - (n % 4)) % 4


def path_bytes(rel):
    """Encode a res:// path the way Godot's PCKPacker does (NUL padded, length includes pad)."""
    raw = rel.encode("utf-8")
    pad = pad4(len(raw) + 1)  # keep the terminating NUL inside a 4-byte slot
    total = len(raw) + 1 + pad
    while total % 4:
        total += 1
    return total.to_bytes(4, "little") + raw + b"\x00" * (total - len(raw))


def to_res_path(rel):
    return "res://" + rel.replace(os.sep, "/")


def collect(root, skip_exts, keep_only=None):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, root)
            ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
            if ext in skip_exts:
                continue
            if keep_only and not any(rel.replace(os.sep, "/").endswith(k) for k in keep_only):
                continue
            out.append((rel, full))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--skip-exts", default="")
    ap.add_argument("--align", type=int, default=16)
    ap.add_argument("--pad-mb", type=float, default=0.0,
                    help="append a dummy res://__pad.bin of this size (memory-ceiling tests)")
    args = ap.parse_args()

    skip = {e.strip().lower() for e in args.skip_exts.split(",") if e.strip()}
    files = collect(args.src, skip)
    pad_bytes = int(args.pad_mb * 1_000_000)
    if pad_bytes:
        pad_path = os.path.join(os.path.dirname(os.path.abspath(args.out)), "__pad.bin")
        os.makedirs(os.path.dirname(pad_path), exist_ok=True)
        with open(pad_path, "wb") as pf:
            pf.truncate(pad_bytes)
        files.append(("__pad.bin", pad_path))
    print(f"{len(files)} files from {args.src}")

    # Pass 1: build the directory to learn its size.
    dir_blob = bytearray()
    for rel, full in files:
        size = os.path.getsize(full)
        dir_blob += path_bytes(to_res_path(rel))
        dir_blob += struct.pack("<QQ", 0, size)  # offsets patched in pass 2
        dir_blob += b"\x00" * 16
        dir_blob += struct.pack("<I", 0)

    file_base = HEADER_SIZE + len(dir_blob)
    file_base += (-file_base) % args.align
    print(f"directory {len(dir_blob):,} bytes, file_base={file_base:,} (0x{file_base:X})")

    # Pass 2: write header + real directory + aligned data.
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "wb") as out:
        hdr = bytearray(HEADER_SIZE)
        hdr[0:4] = b"GDPC"
        struct.pack_into("<IIII", hdr, 4, PACK_FORMAT, *VER)
        struct.pack_into("<I", hdr, 20, 0)  # pack_flags
        struct.pack_into("<Q", hdr, 24, file_base)
        struct.pack_into("<I", hdr, 96, len(files))
        out.write(hdr)

        dir_offset = {}
        for rel, full in files:
            out.write(path_bytes(to_res_path(rel)))
            dir_offset[rel] = out.tell()
            out.write(struct.pack("<QQ", 0, os.path.getsize(full)))
            out.write(b"\x00" * 16)
            out.write(struct.pack("<I", 0))
        assert out.tell() <= file_base, (out.tell(), file_base)
        out.write(b"\x00" * (file_base - out.tell()))

        patches = []
        written = 0
        total = 0
        for i, (rel, full) in enumerate(files):
            pad = (-out.tell()) % args.align
            if pad:
                out.write(b"\x00" * pad)
            ofs = out.tell() - file_base
            with open(full, "rb") as f:
                data = f.read()
            out.write(data)
            digest = hashlib.md5(data).digest()
            patches.append((dir_offset[rel], ofs, len(data), digest))
            written += 1
            total += len(data)
            if written % 500 == 0:
                print(f"  {written}/{len(files)} {total / 1e6:.0f} MB")
        end = out.tell()

        for off, ofs, size, digest in patches:
            out.seek(off)
            out.write(struct.pack("<QQ", ofs, size))
            out.write(digest)

    print(f"wrote {args.out}: {written} files, {total / 1e6:.1f} MB data, "
          f"{end / 1e6:.1f} MB pack")


if __name__ == "__main__":
    main()
