#!/usr/bin/env python3
"""Split web/godot.pck into <100 MB parts for GitHub Pages.

GitHub hard-rejects files larger than 100 MiB at push time, and GitHub Pages
serves files from the repository tree - so the multi-hundred-MB pack cannot be
hosted as one file. This writes web/pck/godot.pck.partNN + manifest.json,
which web/pck_loader.js assembles into a Blob in the browser.

Run order:  build_pack.py -> assemble_web.py -> split_pck.py
(split_pck removes web/godot.pck afterwards; re-running the two build scripts
recreates it.)
"""
import json
import os
import sys

CHUNK = 90_000_000  # safely under GitHub's 100 MiB hard limit


def main():
    web = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "web")
    src = os.path.join(web, "godot.pck")
    if not os.path.exists(src):
        print("godot.pck not found - build it first with build_pack.py")
        return 1
    outdir = os.path.join(web, "pck")
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
    with open(os.path.join(outdir, "manifest.json"), "w") as f:
        json.dump({"parts": parts, "size": total}, f)
    print(f"{len(parts)} parts, {total / 1e6:.1f} MB total -> web/pck/")

    if "--keep" not in sys.argv:
        os.remove(src)
        print("removed web/godot.pck (rebuild: build_pack.py, assemble_web.py, split_pck.py)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
