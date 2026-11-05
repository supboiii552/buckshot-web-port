#!/usr/bin/env python3
"""Dump Godot 4.1 project.binary (ECFG) entries."""
import struct
import sys

PATH = sys.argv[1] if len(sys.argv) > 1 else (
    r"C:\Users\eight\Downloads\Buckshot Roulette_windows\webport\game_data\project.binary")


class R:
    def __init__(self, b):
        self.b = b
        self.p = 0

    def raw(self, n):
        v = self.b[self.p:self.p + n]
        self.p += n
        return v

    def u32(self):
        v = struct.unpack_from("<I", self.b, self.p)[0]
        self.p += 4
        return v

    def i32(self):
        v = struct.unpack_from("<i", self.b, self.p)[0]
        self.p += 4
        return v

    def u64(self):
        v = struct.unpack_from("<Q", self.b, self.p)[0]
        self.p += 8
        return v

    def i64(self):
        v = struct.unpack_from("<q", self.b, self.p)[0]
        self.p += 8
        return v

    def f32(self):
        v = struct.unpack_from("<f", self.b, self.p)[0]
        self.p += 4
        return v

    def f64(self):
        v = struct.unpack_from("<d", self.b, self.p)[0]
        self.p += 8
        return v

    def cstr(self):
        n = self.u32()
        s = self.b[self.p:self.p + n]
        self.p += n
        pad = (4 - n % 4) % 4
        self.p += pad
        return s.decode("utf-8", "replace")


def dec(r, depth=0):
    header = r.u32()
    t = header & 0xFF
    wide = bool(header & (1 << 16))
    if t == 0:
        return None
    if t == 1:
        return bool(r.u32())
    if t == 2:
        return r.i64() if wide else r.i32()
    if t == 3:
        return r.f64() if wide else r.f32()
    if t in (4, 21):
        return r.cstr()
    if t == 5:
        return ("Vector2", r.f64() if wide else r.f32(), r.f64() if wide else r.f32())
    if t == 6:
        return ("Vector2i", r.i32(), r.i32())
    if t == 9:
        return ("Vector3",) + tuple(r.f64() if wide else r.f32() for _ in range(3))
    if t == 10:
        return ("Vector3i", r.i32(), r.i32(), r.i32())
    if t == 11:
        return ("Rect2",) + tuple(r.f64() if wide else r.f32() for _ in range(4))
    if t == 20:
        return ("Color", r.f32(), r.f32(), r.f32(), r.f32())
    if t == 7:
        return ("Rect2",) + tuple(r.f64() if wide else r.f32() for _ in range(4))
    if t == 8:
        return ("Rect2i", r.i32(), r.i32(), r.i32(), r.i32())
    if t == 11:
        return ("Transform2D",) + tuple(r.f64() if wide else r.f32() for _ in range(6))
    if t == 12:
        return ("Vector4",) + tuple(r.f64() if wide else r.f32() for _ in range(4))
    if t == 13:
        return ("Vector4i", r.i32(), r.i32(), r.i32(), r.i32())
    if t == 14:
        return ("Plane",) + tuple(r.f64() if wide else r.f32() for _ in range(4))
    if t == 15:
        return ("Quaternion",) + tuple(r.f64() if wide else r.f32() for _ in range(4))
    if t == 16:
        return ("AABB",) + tuple(r.f64() if wide else r.f32() for _ in range(6))
    if t == 17:
        return ("Basis",) + tuple(r.f64() if wide else r.f32() for _ in range(9))
    if t == 18:
        return ("Transform3D",) + tuple(r.f64() if wide else r.f32() for _ in range(12))
    if t == 19:
        return ("Projection",) + tuple(r.f64() if wide else r.f32() for _ in range(16))
    if t == 22:
        n = r.u32() & 0x7FFFFFFF
        r.u32()
        r.u32()
        return ("NodePath", *[r.cstr() for _ in range(n)])
    if t == 23:  # RID: _encode_uint writes 4 bytes when it fits in u32
        return ("RID", r.u32())
    if t == 24:
        if header & (1 << 16):
            r.u64()
            return ("ObjectID",)
        cls = r.cstr()
        n = r.u32()
        props = {}
        for _ in range(n):
            name = r.cstr()  # must be read BEFORE the value (RHS evaluates first)
            props[name] = dec(r, depth + 1)
        return ("Object", cls, props)
    if t == 27:
        kk = (header >> 16) & 0b11
        vv = (header >> 18) & 0b11
        for kind in (kk, vv):
            if kind == 1:
                r.u32()
            elif kind in (2, 3):
                r.cstr()
        n = r.u32() & 0x7FFFFFFF
        return {str(dec(r, depth + 1)): dec(r, depth + 1) for _ in range(n)}
    if t == 28:
        kind = (header >> 16) & 0b11
        if kind == 1:
            r.u32()
        elif kind in (2, 3):
            r.cstr()
        n = r.u32() & 0x7FFFFFFF
        return [dec(r, depth + 1) for _ in range(n)]
    if t in (29, 30, 31, 32, 33, 34, 35, 36, 37, 38):
        n = r.u32()
        if t == 29:
            r.raw(n + (4 - n % 4) % 4)
        elif t == 30:  # PackedInt32
            r.raw(n * 4)
        elif t == 31:  # PackedInt64
            r.raw(n * 8)
        elif t == 32:  # PackedFloat32
            r.raw(n * 4)
        elif t == 33:  # PackedFloat64
            r.raw(n * 8)
        elif t == 34:  # PackedStringArray
            for _ in range(n):
                r.cstr()
        elif t == 35:  # PackedVector2
            r.raw(n * (8 if wide else 4) * 2)
        elif t == 36:  # PackedVector3
            r.raw(n * (8 if wide else 4) * 3)
        elif t == 37:  # PackedColor
            r.raw(n * 16)
        return f"<packed {t} n={n}>"
    raise ValueError(f"variant type {t} at {r.p - 4}")


def main():
    blob = open(PATH, "rb").read()
    assert blob[:4] == b"ECFG", blob[:4]
    (ver,) = struct.unpack_from("<I", blob, 4)
    print(f"ECFG version {ver}, {len(blob)} bytes")
    r = R(blob[8:])
    entries = {}
    order = []
    while r.p < len(r.b):
        klen = r.u32()
        key = r.raw(klen).decode()
        vlen = r.u32()
        start = r.p
        try:
            val = dec(r)
        except Exception as ex:
            print(f"  FAIL at key {key!r} vlen={vlen} pos={r.p} ({ex})")
            print("   bytes:", r.b[max(0, start - 8):start + 64].hex(" ", 4))
            raise
        got = r.p - start
        if got != vlen:
            print(f"  !! {key}: vlen={vlen} decoded={got}")
        entries[key] = val
        order.append(key)
    print(f"parsed {len(entries)} entries, consumed {r.p}/{len(r.b)}")

    for k in order:
        print(f"\n{k} = {entries[k]}")


if __name__ == "__main__":
    main()
