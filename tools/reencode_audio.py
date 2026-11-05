#!/usr/bin/env python3
"""Shrink Buckshot Roulette's .oggvorbisstr resources.

Godot 4.1 stores each imported Ogg as an RSRC file:
  OggPacketSequence { packet_data: Array<Array<PackedByteArray>> (pages->packets),
                      granule_positions: PackedInt64Array, sampling_rate }
  AudioStreamOggVorbis { packet_sequence: Ref<#0>, loop: bool }

We rebuild the raw Vorbis bitstream into a real .ogg (Ogg pages with CRCs),
re-encode via ffmpeg (libvorbis) at a lower bitrate, split the result back
into pages/packets, and rewrite the resource. loop / sampling_rate are kept.

Sizes with this strategy at 64 kbps:
  old 136.2 MB total -> single-player only (prune mp_) + re-encode.
"""
import argparse
import os
import struct
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import oggpack
import rsrc

FFMPEG = r"C:\tools\ffmpeg.exe"


def extract_packets(blob):
    """Return (pages, grains, stream_props) for an .oggvorbisstr blob."""
    res = rsrc.read(blob)
    seq = audio = None
    for tn, props in res.objects:
        d = dict(props)
        if tn == "OggPacketSequence":
            seq = d
        elif tn == "AudioStreamOggVorbis":
            audio = d
    pd = seq["packet_data"]
    gp = seq["granule_positions"]
    cnt = struct.unpack_from("<I", gp.payload, 0)[0]
    grains = list(struct.unpack_from("<%dq" % cnt, gp.payload, 4))
    pages = [[bytes(x) for x in page] for page in pd]
    return pages, grains, seq, audio, res


def rebuild_ogg(pages, grains):
    return oggpack.packets_to_ogg(pages, grains)


def reencode_ogg(ogg_bytes, bitrate="64k"):
    """Decode and re-encode a .ogg stream, returning new ogg bytes."""
    tmp_in = os.path.join(tempfile.gettempdir(), "_br_in.ogg")
    tmp_out = os.path.join(tempfile.gettempdir(), "_br_out.ogg")
    with open(tmp_in, "wb") as f:
        f.write(ogg_bytes)
    if os.path.exists(tmp_out):
        os.remove(tmp_out)
    rr = subprocess.run(
        [FFMPEG, "-v", "error", "-y", "-i", tmp_in,
         "-c:a", "libvorbis", "-b:a", bitrate, tmp_out],
        capture_output=True)
    if rr.returncode != 0 or not os.path.exists(tmp_out):
        return None
    with open(tmp_out, "rb") as f:
        return f.read()


def ogg_to_resource(new_ogg):
    pages = oggpack.ogg_to_packets(new_ogg)
    sel_pages = [p for _s, _g, p, _ht in pages]
    sel_grains = [g for _s, g, _p, _ht in pages]
    return sel_pages, sel_grains


def rebuild_resource(pages, grains, seq, audio, res):
    """Swap packet_data/granule_positions in the parsed resource."""
    # packet_data: list of pages, each page is a list of packets (bytes)
    new_pd = [[bytes(pkt) for pkt in page] for page in pages]
    new_gp_payload = struct.pack("<I", len(grains))
    new_gp_payload += struct.pack("<%dq" % len(grains), *grains)
    from rsrc import Raw
    for tn, props in res.objects:
        if tn != "OggPacketSequence":
            continue
        d = {(k): v for k, v in props}
        for i, (k, _v) in enumerate(props):
            if k == "packet_data":
                props[i] = (k, new_pd)
            elif k == "granule_positions":
                props[i] = (k, Raw(48, new_gp_payload))
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--min-size-mb", type=float, default=0.3,
                    help="only re-encode files >= this size; others are copied")
    ap.add_argument("--bitrate", default="64k")
    ap.add_argument("--bitrate-music", default="64k")
    ap.add_argument("--skip-prefix", action="append", default=[],
                    help="skip files whose basename starts with any of these "
                         "(e.g. mp_)")
    args = ap.parse_args()

    files = []
    for dp, _dn, fn in os.walk(args.src):
        for f in fn:
            if f.endswith(".oggvorbisstr"):
                base = f
                if any(base.startswith(sfx) for sfx in args.skip_prefix):
                    continue
                files.append(os.path.join(dp, f))

    done = copied = failed = 0
    before = after = 0
    for p in sorted(files):
        rel = os.path.relpath(p, args.src)
        dst = os.path.join(args.out, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        before += os.path.getsize(p)
        blob = open(p, "rb").read()

        if os.path.getsize(p) < args.min_size_mb * 1_000_000:
            open(dst, "wb").write(blob)
            after += len(blob)
            copied += 1
            continue

        try:
            pages, grains, seq, audio, res = extract_packets(blob)
            ogg = rebuild_ogg(pages, grains)
            is_music = bool(audio and audio.get("loop"))
            br = args.bitrate_music if is_music else args.bitrate
            new_ogg = reencode_ogg(ogg, br)
            if new_ogg is None:
                raise RuntimeError("ffmpeg re-encode failed")
            new_pages, new_grains = ogg_to_resource(new_ogg)
            if len(new_pages) < 3:
                raise RuntimeError("re-encoded stream has <3 pages")
            if not any(len(pg) > 0 for pg in new_pages):
                raise RuntimeError("re-encoded stream has no data pages")
            res2 = rebuild_resource(new_pages, new_grains, seq, audio, res)
            out = rsrc.write(res2)
            open(dst, "wb").write(out)
            after += len(out)
            done += 1
            print(f"  {os.path.basename(p)[:44]:46s} "
                  f"{os.path.getsize(p)/1e6:6.2f}MB -> {len(out)/1e6:6.2f}MB"
                  + ("  [music]" if is_music else ""), flush=True)
        except Exception as e:
            # keep original on any failure
            open(dst, "wb").write(blob)
            after += len(blob)
            failed += 1
            print(f"  !! {os.path.basename(p)[:44]:46s} kept original: {e}",
                  flush=True)

    print(f"re-encoded {done}, copied {copied}, failed {failed}: "
          f"{before/1e6:.1f} -> {after/1e6:.1f} MB")


if __name__ == "__main__":
    main()
