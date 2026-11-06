#!/usr/bin/env python3
"""Build the base + 3-device-texture-overlay pack set for the GitHub Pages
deploy (keeps the published tree under GitHub's 1 GB Pages limit).

Layout shipped under docs/:
  base/        base.pck: project, scripts, scenes, audio - everything EXCEPT
               textures (built from build/full with all .ctex excluded)
  tex-s3tc/    overlay with the desktop BC1/BC3 textures (build/assets)
  tex-etc2/    overlay with ETC2/EAC textures (build/assets-etc2)
  tex-rgba/    overlay with uncompressed RGB8/RGBA8/RG8 (build/assets-rgba)

The JS loader assembles base.pck plus its chosen overlay and preloads both
buffers as res://base.pck and res://tex.pck; the BootPack autoload (first in
project.binary) mounts the overlay with replace_files=true at engine boot.

To keep the tree reproducible this script (idempotently):
  1. writes scripts/boot_pack.gd into build/full
  2. patches build/full/project.binary: autoload/BootPack -> boot_pack.gd,
     inserted as the FIRST autoload so it runs before everything else
then packs and splits all four targets:
  build_pack.py -> split_pck.py per pack (--dir base / tex-s3tc / ...)
"""
import os
import struct
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TOOLS = os.path.dirname(os.path.abspath(__file__))
FULL = os.path.join(TOOLS, "..", "build", "full")
BOOT_SRC = os.path.join(TOOLS, "boot_pack.gd")
BOOT_DST = os.path.join(FULL, "scripts", "boot_pack.gd")
PROJ = os.path.join(FULL, "project.binary")

OVERLAYS = {
    "tex-s3tc": os.path.join(TOOLS, "..", "build", "assets"),
    "tex-etc2": os.path.join(TOOLS, "..", "build", "assets-etc2"),
    "tex-rgba": os.path.join(TOOLS, "..", "build", "assets-rgba"),
}


def decode_ecfg(blob):
    assert blob[:4] == b"ECFG", "not an ECFG project.binary"
    count = struct.unpack_from("<I", blob, 4)[0]
    p = 8
    entries = []
    for _ in range(count):
        slen = struct.unpack_from("<I", blob, p)[0]; p += 4
        key = blob[p:p + slen].decode("utf-8"); p += slen
        vlen = struct.unpack_from("<I", blob, p)[0]; p += 4
        entries.append((key, blob[p:p + vlen])); p += vlen
    assert p == len(blob), "trailing bytes"
    return entries


def write_ecfg(path, entries):
    outb = bytearray(b"ECFG")
    outb += struct.pack("<I", len(entries))
    for k, blob in entries:
        kb = k.encode("utf-8")
        outb += struct.pack("<I", len(kb)) + kb
        outb += struct.pack("<I", len(blob)) + blob
    open(path, "wb").write(bytes(outb))


def patch_boot():
    """Idempotently add boot_pack.gd + its autoload to the base tree."""
    with open(BOOT_DST, "w", encoding="utf-8", newline="\n") as f:
        f.write(open(BOOT_SRC, encoding="utf-8").read())

    entries = decode_ecfg(open(PROJ, "rb").read())
    keys = [k for k, _ in entries]
    if "autoload/BootPack" not in keys:
        utf8 = b"*res://scripts/boot_pack.gd\x00"
        while len(utf8) % 4:
            utf8 += b"\x00"  # keep terminating NUL inside a 4-byte slot
        val = struct.pack("<II", 4, len(utf8)) + utf8

        ai = keys.index("autoload/GlobalSteam")
        entries.insert(ai, ("autoload/BootPack", val))
        write_ecfg(PROJ, entries)
        print(f"project.binary patched: autoload/BootPack inserted before GlobalSteam "
              f"({len(entries)} entries)")
    else:
        print("project.binary already patched")


def run(*args):
    print("+", " ".join(args), flush=True)
    subprocess.check_call(args)
    print()


def main():
    patch_boot()
    docs = os.path.join(TOOLS, "..", "docs")
    base_pck = os.path.join(docs, "base.pck")

    # Base keeps the original ctex for any texture the s3tc overlay does not
    # cover (shrink_textures skipped some conversions; the old one-file build
    # backfilled those from the full tree). All remaining base ctex are
    # uncompressed formats, safe to upload on every device.
    s3tc_src = OVERLAYS["tex-s3tc"]
    skip_list = os.path.join(TOOLS, "skip-s3tc.txt")
    with open(skip_list, "w") as sf:
        for dp, _dn, fn in os.walk(s3tc_src):
            for f in fn:
                if f.endswith(".ctex"):  # audio re-encodes stay in base
                    sf.write(os.path.relpath(os.path.join(dp, f), s3tc_src)
                             .replace(os.sep, "/") + "\n")
    print(f"skip list: {sum(1 for _ in open(skip_list))} s3tc-overlay paths")

    run(sys.executable, os.path.join(TOOLS, "build_pack.py"),
        "--src", FULL, "--out", base_pck, "--skip-from", skip_list)
    run(sys.executable, os.path.join(TOOLS, "split_pck.py"),
        "--from", base_pck, "--dir", "base")

    for name, src in OVERLAYS.items():
        overlay_pck = os.path.join(docs, name + ".pck")
        run(sys.executable, os.path.join(TOOLS, "build_pack.py"),
            "--src", src, "--out", overlay_pck)
        run(sys.executable, os.path.join(TOOLS, "split_pck.py"),
            "--from", overlay_pck, "--dir", name)

    dirs = ["base"] + list(OVERLAYS)
    for d in dirs:
        parts = sorted(os.listdir(os.path.join(docs, d)))
        sizes = [os.path.getsize(os.path.join(docs, d, p)) for p in parts]
        print(f"docs/{d}: {len(parts)} files, {sum(sizes) / 1e6:.1f} MB")
    total = 0
    for d in dirs:
        for p in os.listdir(os.path.join(docs, d)):
            total += os.path.getsize(os.path.join(docs, d, p))
    print(f"TOTAL: {total / 1e6:.1f} MB (GitHub Pages limit: 1024 MB)")


if __name__ == "__main__":
    main()
