#!/usr/bin/env python3
"""Rebuild a real .ogg file from an OggPacketSequence's page_data, and split a
real .ogg back into pages. Used to round-trip Buckshot Roulette's
.oggvorbisstr resources through ffmpeg for re-encoding.
"""
import struct

# ------------------------------------------------------------------ tables

_CRC_TABLE = []
for i in range(256):
    crc = i << 24
    for _ in range(8):
        crc = ((crc << 1) ^ (0x04C11DB7 if crc & 0x80000000 else 0)) & 0xFFFFFFFF
    _CRC_TABLE.append(crc)


def _crc(data):
    """Ogg page checksum: non-reflected CRC-32 over header+body with the
    checksum field (bytes 22..25) treated as zero."""
    crc = 0
    for b in data:
        crc = ((crc << 8) ^ _CRC_TABLE[((crc >> 24) & 0xFF) ^ b]) & 0xFFFFFFFF
    return crc


# ------------------------------------------------------------ page building

def _make_page(serial, seqno, granule, header_type, packets):
    """Build one Ogg page from a list of packet byte arrays."""
    seg = bytearray()
    body = bytearray()
    for pkt in packets:
        for off in range(0, len(pkt), 255):
            n = min(255, len(pkt) - off)
            seg.append(n)
            body += pkt[off:off + n]
        # a packet that is an exact multiple of 255 still needs a trailing 0
        if len(pkt) % 255 == 0:
            seg.append(0)
    hdr = b"OggS\x00"
    hdr += bytes([header_type])  # 0x02 BOS, 0x04 cont, 0x01 EOS
    hdr += struct.pack("<Q", granule)
    hdr += struct.pack("<I", serial)
    hdr += struct.pack("<I", seqno)
    hdr += struct.pack("<I", 0)  # CRC, patched below
    hdr += bytes([len(seg)])
    page = bytearray(hdr + seg + body)
    crc = _crc(page)
    struct.pack_into("<I", page, 22, crc)
    return bytes(page)


def packets_to_ogg(pages, granules, serial=0x1999B3E3):
    """pages: list of list-of-bytes; granules: list of int (per page)."""
    out = bytearray()
    n = len(pages)
    for i, pkts in enumerate(pages):
        header_type = 0x02 if i == 0 else 0x00
        if i == n - 1:
            header_type |= 0x01
        granule = granules[i] if i < len(granules) else -1
        out += _make_page(serial, i, granule, header_type, pkts)
    return bytes(out)


# -------------------------------------------------------------- page parsing

def ogg_to_packets(data):
    """Parse a .ogg byte stream into (pages, granules). Each page keeps
    absolute serial; pages with different serials are separate logical
    streams but we keep one list (the audio stream is the one with packets).
    """
    pages = []           # list of (serial, granule, [packets])
    pos = 0
    while pos + 27 <= len(data):
        if data[pos:pos + 4] != b"OggS":
            pos += 1
            continue
        version = data[pos + 4]
        header_type = data[pos + 5]
        granule = struct.unpack_from("<Q", data, pos + 6)[0]
        serial = struct.unpack_from("<I", data, pos + 14)[0]
        seq = struct.unpack_from("<I", data, pos + 18)[0]
        nsegs = data[pos + 26]
        segs = list(data[pos + 27: pos + 27 + nsegs])
        body_start = pos + 27 + nsegs
        packets = []
        cur = bytearray()
        body_pos = body_start
        for s in segs:
            cur += data[body_pos: body_pos + s]
            body_pos += s
            if s < 255:
                packets.append(bytes(cur))
                cur = bytearray()
        if cur:
            packets.append(bytes(cur))
        pages.append((serial, granule, packets, header_type))
        pos = body_start + sum(segs)
    return pages


def pick_audio_stream(pages):
    """Buckshot .oggvorbisstr are a single stream, but be safe."""
    best = None
    counts = {}
    for serial, _granule, packets, _ht in pages:
        counts.setdefault(serial, 0)
        counts[serial] += len(packets)
    serial = max(counts, key=counts.get)
    sel = [(g, p) for s, g, p, ht in pages if s == serial]
    # ensure at least one page
    return [p for _g, p in sel], [g for g, _p in sel]
