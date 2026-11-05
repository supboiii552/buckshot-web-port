#!/usr/bin/env python3
"""Minimal Godot 4.x binary resource (.res / RSRC) reader + writer.

Only what the web port needs: read an exported resource, change a couple of
variants, write it back with the same layout.

Header (4.1, FORMAT_VERSION 5):
  'RSRC'
  u32 big_endian, u32 use_real64
  u32 ver_major, u32 ver_minor, u32 format_version
  unicode_string class
  u64 import_md_offset
  u32 format_flags
  u64 uid
  [unicode_string script_class  if flags & 8]
  u32 reserved[11]
  u32 string_count, unicode_string * n
  u32 external_count, (unicode class, unicode path, u64 uid) * n
  u32 internal_count, (unicode path, u64 offset) * n
  <resource bodies at the recorded offsets>
"""
import struct

VARIANT_NIL = 1
VARIANT_BOOL = 2
VARIANT_INT = 3
VARIANT_FLOAT = 4
VARIANT_STRING = 5
VARIANT_VECTOR2 = 10
VARIANT_RECT2 = 11
VARIANT_VECTOR3 = 12
VARIANT_PLANE = 13
VARIANT_QUATERNION = 14
VARIANT_AABB = 15
VARIANT_BASIS = 16
VARIANT_TRANSFORM3D = 17
VARIANT_TRANSFORM2D = 18
VARIANT_COLOR = 20
VARIANT_NODE_PATH = 22
VARIANT_RID = 23
VARIANT_OBJECT = 24
VARIANT_INPUT_EVENT = 25
VARIANT_DICTIONARY = 26
VARIANT_ARRAY = 30
VARIANT_PACKED_BYTE_ARRAY = 31
VARIANT_PACKED_INT32_ARRAY = 32
VARIANT_PACKED_FLOAT32_ARRAY = 33
VARIANT_PACKED_STRING_ARRAY = 34
VARIANT_PACKED_VECTOR3_ARRAY = 35
VARIANT_PACKED_COLOR_ARRAY = 36
VARIANT_PACKED_VECTOR2_ARRAY = 37
VARIANT_INT64 = 40
VARIANT_DOUBLE = 41
VARIANT_CALLABLE = 42
VARIANT_SIGNAL = 43
VARIANT_STRING_NAME = 44
VARIANT_VECTOR2I = 45
VARIANT_RECT2I = 46
VARIANT_VECTOR3I = 47
VARIANT_PACKED_INT64_ARRAY = 48
VARIANT_PACKED_FLOAT64_ARRAY = 49
VARIANT_VECTOR4 = 50
VARIANT_VECTOR4I = 51
VARIANT_PROJECTION = 52

OBJECT_EMPTY = 0
OBJECT_EXTERNAL_RESOURCE = 1
OBJECT_INTERNAL_RESOURCE = 2
OBJECT_EXTERNAL_RESOURCE_INDEX = 3


class Ref:
    """Reference to an internal (built-in) sub-resource."""

    def __init__(self, index):
        self.index = index

    def __repr__(self):
        return f"Ref(#{self.index})"


class Raw:
    """A variant we keep byte-identical (packed arrays we never edit)."""

    def __init__(self, type_id, payload):
        self.type_id = type_id
        self.payload = payload

    def __repr__(self):
        return f"Raw({self.type_id}, {len(self.payload)}B)"


class Reader:
    def __init__(self, blob):
        self.b = blob
        self.p = 0

    def u32(self):
        v = struct.unpack_from("<I", self.b, self.p)[0]
        self.p += 4
        return v

    def i32(self):
        v = struct.unpack_from("<i", self.b, self.p)[0]
        self.p += 4
        return v

    def i64(self):
        v = struct.unpack_from("<q", self.b, self.p)[0]
        self.p += 8
        return v

    def u64(self):
        v = struct.unpack_from("<Q", self.b, self.p)[0]
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

    def raw(self, n):
        v = self.b[self.p:self.p + n]
        self.p += n
        return v

    def ustr(self):
        n = self.u32() & 0x7FFFFFFF  # bit 31 flags a UTF-8 NodePath name
        s = self.b[self.p:self.p + n]
        self.p += n
        return s.rstrip(b"\x00").decode("utf-8", "replace")


REAL = "f"  # per-file (f32 or f64 depending on use_real64)


class Resource:
    def __init__(self):
        self.big_endian = 0
        self.use_real64 = 0
        self.ver_major = 4
        self.ver_minor = 1
        self.format_version = 5
        self.class_name = ""
        self.import_md = 0
        self.format_flags = 0
        self.uid = 0
        self.script_class = ""
        self.strings = []
        self.external = []      # list of (class, path, uid)
        self.internal = []      # list of [path, offset]
        self.objects = []       # list of (type_name, [(prop_name, value)])


def read(blob, has_magic=True):
    r = Reader(blob)
    if has_magic:
        assert blob[:4] == b"RSRC", blob[:4]
        r.p = 4
    else:
        r.p = 0
    res = Resource()
    res.big_endian = r.u32()
    res.use_real64 = r.u32()
    res.ver_major = r.u32()
    res.ver_minor = r.u32()
    res.format_version = r.u32()
    res.class_name = r.ustr()
    res.import_md = r.u64()
    res.format_flags = r.u32()
    res.uid = r.u64()
    if res.format_flags & 8:
        res.script_class = r.ustr()
    r.raw(4 * 11)

    n = r.u32()
    res.strings = [r.ustr() for _ in range(n)]
    n = r.u32()
    for _ in range(n):
        cls = r.ustr()
        path = r.ustr()
        uid = r.u64()
        res.external.append((cls, path, uid))
    n = r.u32()
    for _ in range(n):
        path = r.ustr()
        ofs = r.u64()
        res.internal.append([path, ofs])

    for path, ofs in res.internal:
        r.p = ofs
        type_name = r.ustr()
        nprops = r.u32()
        props = []
        for _ in range(nprops):
            idx = r.u32()
            name = res.strings[idx] if idx < len(res.strings) else f"#{idx}"
            props.append((name, read_variant(r, res)))
        res.objects.append((type_name, props))
    return res


def read_variant(r, res=None):
    t = r.u32()
    if t == VARIANT_NIL:
        return None
    if t == VARIANT_BOOL:
        return bool(r.u32())
    if t == VARIANT_INT:
        return r.i32()
    if t == VARIANT_INT64:
        return r.i64()
    if t == VARIANT_FLOAT:
        return r.f32()
    if t == VARIANT_DOUBLE:
        return r.f64()
    if t in (VARIANT_STRING, VARIANT_STRING_NAME):
        return r.ustr()
    if t == VARIANT_OBJECT:
        kind = r.u32()
        if kind == OBJECT_EMPTY:
            return None
        if kind == OBJECT_INTERNAL_RESOURCE:
            return Ref(r.u32())
        if kind == OBJECT_EXTERNAL_RESOURCE_INDEX:
            return ("ext", r.u32())
        if kind == OBJECT_EXTERNAL_RESOURCE:
            cls = r.ustr()
            path = r.ustr()
            return ("ext_path", cls, path)
        raise ValueError(f"object kind {kind} at {r.p}")
    if t == VARIANT_ARRAY:
        n = r.u32()
        return [read_variant(r, res) for _ in range(n)]
    if t == VARIANT_DICTIONARY:
        n = r.u32()
        out = {}
        for _ in range(n):
            k = read_variant(r, res)
            v = read_variant(r, res)
            out[str(k)] = v
        return out
    if t == VARIANT_PACKED_BYTE_ARRAY:
        n = r.u32()
        data = r.raw(n)
        pad = (4 - n % 4) % 4
        if pad:
            r.raw(pad)
        return bytes(data)
    # ---- everything else: capture bytes verbatim ----
    start = r.p
    _skip_fixed(r, t)
    return Raw(t, r.b[start:r.p])


_FIXED = {
    VARIANT_VECTOR2: 8, VARIANT_VECTOR2I: 8, VARIANT_RECT2: 16, VARIANT_RECT2I: 16,
    VARIANT_VECTOR3: 12, VARIANT_VECTOR3I: 12, VARIANT_PLANE: 16, VARIANT_QUATERNION: 16,
    VARIANT_AABB: 24, VARIANT_BASIS: 36, VARIANT_TRANSFORM3D: 48, VARIANT_TRANSFORM2D: 24,
    VARIANT_COLOR: 16, VARIANT_VECTOR4: 16, VARIANT_VECTOR4I: 16, VARIANT_PROJECTION: 64,
    VARIANT_CALLABLE: 0, VARIANT_SIGNAL: 0,
}


def _skip_fixed(r, t):
    if t in _FIXED:
        r.raw(_FIXED[t])
        return
    if t == VARIANT_NODE_PATH:
        # 4.1 encoding: u16 name count + u16 subname count (bit 15 = absolute)
        n = struct.unpack_from("<H", r.b, r.p)[0]
        sub = struct.unpack_from("<H", r.b, r.p + 2)[0] & 0x7FFF
        r.p += 4
        for _ in range(n + sub):
            r.ustr()
        return
    if t == VARIANT_RID:
        r.raw(4)
        return
    if t in (VARIANT_PACKED_INT32_ARRAY, VARIANT_PACKED_FLOAT32_ARRAY):
        n = r.u32()
        r.raw(n * 4)
        return
    if t in (VARIANT_PACKED_INT64_ARRAY, VARIANT_PACKED_FLOAT64_ARRAY):
        n = r.u32()
        r.raw(n * 8)
        return
    if t == VARIANT_PACKED_STRING_ARRAY:
        n = r.u32()
        for _ in range(n):
            r.ustr()
        return
    if t == VARIANT_PACKED_VECTOR3_ARRAY:
        n = r.u32()
        r.raw(n * 12)
        return
    if t == VARIANT_PACKED_VECTOR2_ARRAY:
        n = r.u32()
        r.raw(n * 8)
        return
    if t == VARIANT_PACKED_COLOR_ARRAY:
        n = r.u32()
        r.raw(n * 16)
        return
    raise ValueError(f"unhandled variant type {t} at {r.p - 4}")


# ------------------------------------------------------------------ writer

class Writer:
    def __init__(self):
        self.out = bytearray()

    def u32(self, v):
        self.out += struct.pack("<I", v & 0xFFFFFFFF)

    def i32(self, v):
        self.out += struct.pack("<i", v)

    def i64(self, v):
        self.out += struct.pack("<q", v)

    def u64(self, v):
        self.out += struct.pack("<Q", v & 0xFFFFFFFFFFFFFFFF)

    def f32(self, v):
        self.out += struct.pack("<f", v)

    def f64(self, v):
        self.out += struct.pack("<d", v)

    def raw(self, b):
        self.out += b

    def ustr(self, s):
        b = s.encode("utf-8") + b"\x00"
        self.u32(len(b))
        self.out += b

    def tell(self):
        return len(self.out)


def write_variant(w, v):
    if v is None:
        w.u32(VARIANT_NIL)
    elif isinstance(v, bool):
        w.u32(VARIANT_BOOL)
        w.u32(1 if v else 0)
    elif isinstance(v, int):
        if v > 0x7FFFFFFF or v < -0x80000000:
            w.u32(VARIANT_INT64)
            w.i64(v)
        else:
            w.u32(VARIANT_INT)
            w.i32(v)
    elif isinstance(v, float):
        fl = struct.unpack("<f", struct.pack("<f", v))[0]
        if float(fl) != v:
            w.u32(VARIANT_DOUBLE)
            w.f64(v)
        else:
            w.u32(VARIANT_FLOAT)
            w.f32(v)
    elif isinstance(v, str):
        w.u32(VARIANT_STRING)
        w.ustr(v)
    elif isinstance(v, (bytes, bytearray)):
        w.u32(VARIANT_PACKED_BYTE_ARRAY)
        w.u32(len(v))
        w.raw(bytes(v))
        pad = (4 - len(v) % 4) % 4
        if pad:
            w.raw(b"\x00" * pad)
    elif isinstance(v, list):
        w.u32(VARIANT_ARRAY)
        w.u32(len(v))
        for item in v:
            write_variant(w, item)
    elif isinstance(v, dict):
        w.u32(VARIANT_DICTIONARY)
        w.u32(len(v))
        for k, val in v.items():
            write_variant(w, k)
            write_variant(w, val)
    elif isinstance(v, Ref):
        w.u32(VARIANT_OBJECT)
        w.u32(OBJECT_INTERNAL_RESOURCE)
        w.u32(v.index)
    elif isinstance(v, tuple) and v and v[0] == "ext":
        w.u32(VARIANT_OBJECT)
        w.u32(OBJECT_EXTERNAL_RESOURCE_INDEX)
        w.u32(v[1])
    elif isinstance(v, tuple) and v and v[0] == "ext_path":
        w.u32(VARIANT_OBJECT)
        w.u32(OBJECT_EXTERNAL_RESOURCE)
        w.ustr(v[1])
        w.ustr(v[2])
    elif isinstance(v, Raw):
        w.u32(v.type_id)
        w.raw(v.payload)
    else:
        raise TypeError(f"cannot encode {type(v)}: {v!r}")


def write(res, has_magic=True):
    w = Writer()
    if has_magic:
        w.raw(b"RSRC")
    w.u32(res.big_endian)
    w.u32(res.use_real64)
    w.u32(res.ver_major)
    w.u32(res.ver_minor)
    w.u32(res.format_version)
    w.ustr(res.class_name)
    w.u64(res.import_md)
    w.u32(res.format_flags)
    w.u64(res.uid)
    if res.format_flags & 8:
        w.ustr(res.script_class)
    w.raw(b"\x00" * (4 * 11))

    w.u32(len(res.strings))
    for s in res.strings:
        w.ustr(s)
    w.u32(len(res.external))
    for cls, path, uid in res.external:
        w.ustr(cls)
        w.ustr(path)
        w.u64(uid)
    w.u32(len(res.internal))
    ofs_pos = []
    for path, _ in res.internal:
        w.ustr(path)
        ofs_pos.append(w.tell())
        w.u64(0)

    bodies = []
    for type_name, props in res.objects:
        bodies.append((w.tell(), type_name, props))
        w.ustr(type_name)
        w.u32(len(props))
        for name, val in props:
            w.u32(res.strings.index(name))
            write_variant(w, val)

    for pos, (body_pos, _, _) in zip(ofs_pos, bodies):
        struct.pack_into("<Q", w.out, pos, body_pos)
    w.raw(b"RSRC")  # trailing magic (FileAccess ends with it too)
    return bytes(w.out)


# ------------------------------------------------------- compressed container

RSCC_MAGIC = b"RSCC"
CMODE_FASTLZ = 0
CMODE_DEFLATE = 1
CMODE_ZSTD = 2
CMODE_GZIP = 3


def is_compressed(blob):
    return blob[:4] == RSCC_MAGIC


def rscc_decompress(blob):
    """Unwrap Godot's FileAccessCompressed container ('RSCC')."""
    import zlib

    if blob[:4] != RSCC_MAGIC:
        raise ValueError("not an RSCC file")
    cmode, block_size, total = struct.unpack_from("<III", blob, 4)
    if block_size == 0:
        raise ValueError("RSCC block size 0 (corrupt)")
    block_count = total // block_size + 1
    p = 16
    sizes = list(struct.unpack_from("<%dI" % block_count, blob, p))
    p += 4 * block_count

    out = bytearray()
    for i, csize in enumerate(sizes):
        chunk = blob[p:p + csize]
        p += csize
        if i == block_count - 1:
            want = total % block_size
        else:
            want = block_size
        if cmode == CMODE_ZSTD:
            import zstandard
            data = zstandard.ZstdDecompressor().decompress(chunk, max_output_size=max(want, 1))
        elif cmode == CMODE_DEFLATE:
            data = zlib.decompress(chunk)
        elif cmode == CMODE_GZIP:
            data = zlib.decompress(chunk, 16 + zlib.MAX_WBITS)
        else:
            raise ValueError(f"unsupported compression mode {cmode}")
        out += data
    if len(out) != total:
        raise ValueError(f"RSCC size mismatch: {len(out)} != {total}")
    return bytes(out)


def rscc_compress(payload, block_size=4096, cmode=CMODE_ZSTD):
    """Wrap a resource in Godot's FileAccessCompressed container."""
    import zlib

    total = len(payload)
    block_count = total // block_size + 1
    blocks = []
    for i in range(block_count):
        start = i * block_size
        chunk = payload[start:start + block_size]
        if cmode == CMODE_ZSTD:
            import zstandard
            blocks.append(zstandard.ZstdCompressor().compress(chunk))
        elif cmode == CMODE_DEFLATE:
            blocks.append(zlib.compress(chunk))
        elif cmode == CMODE_GZIP:
            co = zlib.compressobj(wbits=16 + zlib.MAX_WBITS)
            blocks.append(co.compress(chunk) + co.flush())
        else:
            raise ValueError(f"unsupported compression mode {cmode}")

    out = bytearray()
    out += RSCC_MAGIC
    out += struct.pack("<III", cmode, block_size, total)
    for b in blocks:
        out += struct.pack("<I", len(b))
    for b in blocks:
        out += b
    out += RSCC_MAGIC
    return bytes(out)


def read_any(blob):
    """Read a resource, transparently unwrapping RSCC. Returns (resource, wrapped)."""
    if is_compressed(blob):
        return read(rscc_decompress(blob), has_magic=False), True
    return read(blob), False


def write_any(res, wrapped, block_size=4096, cmode=CMODE_ZSTD):
    if wrapped:
        return rscc_compress(write(res, has_magic=False), block_size, cmode)
    return write(res, has_magic=True)


def find_prop(props, name):
    for k, v in props:
        if k == name:
            return v
    return None


def set_prop(props, name, value):
    for i, (k, _) in enumerate(props):
        if k == name:
            props[i] = (k, value)
            return True
    return False
