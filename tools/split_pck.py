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
    with open(os.path.join(outdir, "manifest.json"), "w") as f:
        json.dump({"parts": parts, "size": total, "version": version}, f)
    print(f"manifest version: {version}")


def main():
    web = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs")
    src = os.path.join(web, "godot.pck")
    outdir = os.path.join(web, "pck")

    if "--manifest-only" in sys.argv:
        if not os.path.isdir(outdir):
            print("no pck/ directory")
            return 1
        parts = sorted(
            f"pck/{f}" for f in os.listdir(outdir) if f.startswith("godot.pck.part"))
        total = sum(os.path.getsize(os.path.join(outdir, os.path.basename(p))) for p in parts)
        write_manifest(outdir, parts, total)
        print(f"{len(parts)} existing parts, {total / 1e6:.1f} MB -> manifest refreshed")
        return 0

    if not os.path.exists(src):
        print("godot.pck not found - build it first with build_pack.py")
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
            parts.append(f"pck/{name}")
            print(f"  {name}: {len(data) / 1e6:.1f} MB")
            i += 1
    write_manifest(outdir, parts, total)
    print(f"{len(parts)} parts, {total / 1e6:.1f} MB total -> docs/pck/")

    if "--keep" not in sys.argv:
        os.remove(src)
        print("removed docs/godot.pck (rebuild: build_pack.py, assemble_web.py, split_pck.py)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
