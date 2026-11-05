#!/usr/bin/env python3
"""Check whether MP-only imported assets (mp_*.ctex / mp_*.oggvorbisstr) are
referenced by anything a web player would load in single-player:
autoloads, and non-multiplayer scenes/resources/scripts."""
import os
import re
import struct

ROOT = r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\game_data"
OUT = []


def note(s):
    OUT.append(s)


# --- autoloads ---------------------------------------------------------------
# decode project.binary ECFG and list autoload/* values
proj = os.path.join(ROOT, "project.binary")
blob = open(proj, "rb").read()
count = struct.unpack_from("<I", blob, 4)[0]
p = 8
for _ in range(count):
    slen = struct.unpack_from("<I", blob, p)[0]; p += 4
    key = blob[p:p + slen].decode("utf-8"); p += slen
    vlen = struct.unpack_from("<I", blob, p)[0]; p += 4
    val = blob[p:p + vlen]; p += vlen
    if key.startswith("autoload/"):
        # value is marshall-encoded string; just extract printable ascii
        txt = re.sub(rb"[^\x20-\x7e]", b"", val).decode("ascii", "replace")
        note(f"autoload {key} -> {txt}")

# --- mp_ imported asset names ------------------------------------------------
imp = os.path.join(ROOT, ".godot", "imported")
mp_assets = [f for f in os.listdir(imp) if f.lower().startswith("mp_") and
             (f.endswith(".ctex") or f.endswith(".oggvorbisstr"))]
sizes = sum(os.path.getsize(os.path.join(imp, f)) for f in mp_assets)
note(f"mp_ imported assets: {len(mp_assets)} files, {sizes/1e6:.1f} MB")

# --- who references them? ----------------------------------------------------
# search every non-imported file (scripts, scenes, resources) for 'mp_' asset
# mentions, and classify by whether the referencing file itself is mp-named
pat = re.compile(rb"mp_[A-Za-z0-9 _\-]+?\.(?:png|jpg|ogg|wav|tscn|scn|gd|res)")
refs_by_file = {}
for dp, dn, fn in os.walk(ROOT):
    if os.path.abspath(dp) == os.path.abspath(imp):
        continue
    for f in fn:
        path = os.path.join(dp, f)
        if os.path.getsize(path) > 40 * 1024 * 1024:
            continue  # skip huge blobs
        try:
            data = open(path, "rb").read()
        except OSError:
            continue
        hits = set(m.group(0).decode("ascii", "replace") for m in pat.finditer(data))
        if hits:
            refs_by_file[os.path.relpath(path, ROOT)] = hits

mp_ref_files = {k for k in refs_by_file if "mp_" in os.path.basename(k).lower()
                or "multiplayer" in k.lower() or "lobby" in k.lower()}
other_ref_files = {k: v for k, v in refs_by_file.items() if k not in mp_ref_files}

note(f"files referencing mp_ assets: {len(refs_by_file)} total, "
     f"{len(mp_ref_files)} are themselves MP files")
note("NON-MP files referencing mp_ assets:")
for k in sorted(other_ref_files):
    sample = sorted(other_ref_files[k])[:6]
    note(f"   {k}: {sample}")

with open(r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\diag\mp_refs.txt",
          "w", encoding="utf-8") as f:
    f.write("\n".join(OUT))
print("written diag/mp_refs.txt, lines:", len(OUT))
