#!/usr/bin/env python3
"""Split docs/godot.pck into <100 MB parts for GitHub Pages.

GitHub hard-rejects files larger than 100 MiB at push time, and GitHub Pages
serves files from the repository tree - so the multi-hundred-MB pack cannot be
hosted as one file. This writes docs/pck/godot.pck.partNN + manifest.json,
which docs/pck_loader.js assembles into a Blob in the browser.

Run order:  build_pack.py -> assemble_web.py -> split_pck.py
(split_pck removes docs/godot.pck afterwards; re-running the two build scripts
recreates it.)
"""
import hashlib
import json
import os
import sys

CHUNK = 90_000_000  # safely under GitHub's 100 MiB hard limit


def pack_md5(paths):
    """md5 of the pack = md5 over its chunks in order (streams, no big buffer)."""
    h = hashlib.md5()
    for p in paths:
        with open(p, "rb") as f:
            while True:
                b = f.read(1 << 20)
                if not b:
                    break
                h.update(b)
    return h.hexdigest()


def write_manifest(outdir, parts, total):
    version = pack_md5([os.path.join(outdir, os.path.basename(p)) for p in parts])
    sizes = [os.path.getsize(os.path.join(outdir, os.path.basename(p))) for p in parts]
    with open(os.path.join(outdir, "manifest.json"), "w") as f:
        json.dump({"parts": parts, "partSizes": sizes, "size": total,
                   "version": version}, f)
    print(f"manifest version: {version}")


def main():
    web = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs")
    argv = sys.argv[1:]
    src = None
    packdir = "pck"
    i = 0
    while i < len(argv):
        if argv[i] == "--from":
            src = argv[i + 1]; i += 2; continue
        if argv[i] == "--dir":
            packdir = argv[i + 1]; i += 2; continue
        i += 1
    outdir = os.path.join(web, packdir)

    if "--manifest-only" in argv:
        if not os.path.isdir(outdir):
            print("no pack directory:", outdir)
            return 1
        parts = sorted(
            f"{packdir}/{f}" for f in os.listdir(outdir) if f.startswith("godot.pck.part"))
        total = sum(os.path.getsize(os.path.join(outdir, os.path.basename(p))) for p in parts)
        write_manifest(outdir, parts, total)
        print(f"{len(parts)} existing parts, {total / 1e6:.1f} MB -> manifest refreshed")
        return 0

    if not src or not os.path.exists(src):
        print("usage: split_pck.py --from <godot.pck> --dir pck [--keep]")
        print("       split_pck.py --dir pck --manifest-only")
        return 1
    os.makedirs(outdir, exist_ok=True)
    for f in os.listdir(outdir):
        os.remove(os.path.join(outdir, f))

    total = os.path.getsize(src)
    parts = []
    with open(src, "rb") as f:
        i = 0
        while True:
            data = f.read(CHUNK)
            if not data:
                break
            name = f"godot.pck.part{i:02d}"
            with open(os.path.join(outdir, name), "wb") as o:
                o.write(data)
            parts.append(f"{packdir}/{name}")
            print(f"  {name}: {len(data) / 1e6:.1f} MB")
            i += 1
    write_manifest(outdir, parts, total)
    print(f"{len(parts)} parts, {total / 1e6:.1f} MB total -> docs/{packdir}/")

    if "--keep" not in argv:
        os.remove(src)
    return 0


if __name__ == "__main__":
    sys.exit(main())
