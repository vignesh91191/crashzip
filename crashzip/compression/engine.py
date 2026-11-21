"""crashzip core: lossless, chunked, float-aware compression container.

Pipeline per chunk (all lossless, bit-exact on decompress):

    raw bytes -> [optional XOR-delta on 32-bit words] -> [byte-plane shuffle]
              -> entropy/LZ codec (zstd | xz/LZMA | brotli)

Why this helps on crash-simulation data (LS-DYNA d3plot, Radioss, PAM-CRASH
style binaries): they are dominated by float32 arrays (coordinates,
displacements, stresses) that change smoothly between time states.

* Byte-plane shuffle groups all sign/exponent bytes together, all top-mantissa
  bytes together, etc., which general-purpose codecs compress far better.
* XOR-delta against the previous word (stride 1) or against the same value in
  the previous time state (stride = state size in 32-bit words) zeroes out the
  bits that did not change between neighbours.

Every file stores a SHA-256 of the original; decompression verifies it.
"""

from __future__ import annotations

import hashlib
import lzma
import os
import struct
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from typing import BinaryIO, Callable, Iterable, Iterator

import numpy as np
import zstandard

try:  # optional
    import brotli  # type: ignore
except ImportError:  # pragma: no cover
    brotli = None

MAGIC = b"CZIP"
VERSION = 1
DEFAULT_CHUNK = 8 * 1024 * 1024

# transforms
T_NONE, T_SHUF, T_XOR1, T_XORS = 0, 1, 2, 3
# codecs
C_STORED, C_ZSTD, C_XZ, C_BROTLI = 0, 1, 2, 3
CODEC_IDS = {"zstd": C_ZSTD, "xz": C_XZ, "brotli": C_BROTLI}

_HDR = struct.Struct("<4sBBIIQI32sH")  # magic ver rsv chunk stride size nchunks sha namelen
_CHK = struct.Struct("<BBII")  # transform codec raw_len comp_len


class CrashZipError(Exception):
    pass


class ChecksumError(CrashZipError):
    pass


# --------------------------------------------------------------------------
# transforms
# --------------------------------------------------------------------------
def _xor_fwd(words: np.ndarray, s: int) -> np.ndarray:
    out = words.copy()
    if s < len(words):
        out[s:] = words[s:] ^ words[:-s]
    return out


def _xor_inv(words: np.ndarray, s: int) -> np.ndarray:
    n = len(words)
    if n == 0:
        return words
    pad = (-n) % s
    p = np.concatenate([words, np.zeros(pad, dtype=words.dtype)]) if pad else words
    out = np.bitwise_xor.accumulate(p.reshape(-1, s), axis=0).reshape(-1)
    return out[:n]


def _forward(data: bytes, tid: int, stride: int) -> bytes:
    if tid == T_NONE:
        return data
    n4 = len(data) // 4
    body = np.frombuffer(data, dtype="<u4", count=n4)
    tail = data[n4 * 4:]
    if tid == T_XOR1:
        body = _xor_fwd(body, 1)
    elif tid == T_XORS:
        body = _xor_fwd(body, stride)
    body = np.ascontiguousarray(body)
    planes = body.view(np.uint8).reshape(-1, 4).T.tobytes()
    return planes + tail


def _inverse(buf: bytes, tid: int, stride: int, raw_len: int) -> bytes:
    if tid == T_NONE:
        return buf
    n4 = raw_len // 4
    tail = buf[n4 * 4:]
    inter = np.frombuffer(buf, dtype=np.uint8, count=n4 * 4).reshape(4, n4).T.reshape(-1)
    words = np.ascontiguousarray(inter).view("<u4")
    if tid == T_XOR1:
        words = _xor_inv(words, 1)
    elif tid == T_XORS:
        words = _xor_inv(words, stride)
    return np.ascontiguousarray(words).tobytes() + tail


# --------------------------------------------------------------------------
# codecs
# --------------------------------------------------------------------------
def _comp(codec: int, data: bytes, level: int) -> bytes:
    if codec == C_ZSTD:
        return zstandard.ZstdCompressor(level=max(1, min(level, 22))).compress(data)
    if codec == C_XZ:
        return lzma.compress(data, format=lzma.FORMAT_RAW,
                             filters=[{"id": lzma.FILTER_LZMA2, "preset": max(0, min(level, 9))}])
    if codec == C_BROTLI:
        if brotli is None:
            raise CrashZipError("brotli module not installed (pip install brotli)")
        return brotli.compress(data, quality=max(0, min(level, 11)))
    raise CrashZipError(f"unknown codec {codec}")


def _decomp(codec: int, data: bytes, raw_len_hint: int, tid_len: int) -> bytes:
    if codec == C_STORED:
        return data
    if codec == C_ZSTD:
        return zstandard.ZstdDecompressor().decompress(data, max_output_size=tid_len)
    if codec == C_XZ:
        return lzma.decompress(data, format=lzma.FORMAT_RAW,
                               filters=[{"id": lzma.FILTER_LZMA2, "preset": 6}])
    if codec == C_BROTLI:
        if brotli is None:
            raise CrashZipError("brotli module not installed (pip install brotli)")
        return brotli.decompress(data)
    raise CrashZipError(f"unknown codec {codec}")


# --------------------------------------------------------------------------
# chunk workers (top level so they pickle for multiprocessing)
# --------------------------------------------------------------------------
def _encode_chunk(args):
    data, stride, codec, level = args
    cands = [T_NONE, T_SHUF, T_XOR1]
    if stride > 1:
        cands.append(T_XORS)
    if len(data) < 256:
        cands = [T_NONE]
    fwd = {}
    best_t, best_sz = T_NONE, None
    for t in cands:
        f = _forward(data, t, stride)
        fwd[t] = f
        sz = len(zstandard.ZstdCompressor(level=1).compress(f))  # quick trial
        if best_sz is None or sz < best_sz:
            best_t, best_sz = t, sz
    payload = _comp(codec, fwd[best_t], level)
    if len(payload) >= len(data):
        return T_NONE, C_STORED, len(data), data
    return best_t, codec, len(data), payload


def _decode_chunk(args):
    tid, codec, raw_len, payload, stride = args
    buf = _decomp(codec, payload, raw_len, raw_len + 8)
    out = _inverse(buf, tid, stride, raw_len)
    if len(out) != raw_len:
        raise CrashZipError("chunk length mismatch (corrupt archive)")
    return out


def _windowed_map(fn: Callable, items: Iterable, workers: int) -> Iterator:
    """Ordered parallel map with a bounded in-flight window (bounded RAM)."""
    if workers <= 1:
        for it in items:
            yield fn(it)
        return
    with ProcessPoolExecutor(max_workers=workers) as ex:
        pending: deque = deque()
        for it in items:
            pending.append(ex.submit(fn, it))
            if len(pending) >= workers * 2:
                yield pending.popleft().result()
        while pending:
            yield pending.popleft().result()


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------
def compress_file(src: str, dst: str, *, codec: str = "zstd", level: int = 15,
                  stride: int = 0, chunk_size: int = DEFAULT_CHUNK,
                  workers: int | None = None, progress: Callable[[int, int], None] | None = None) -> dict:
    """Compress src -> dst. stride = size of one time state in 32-bit words (0 = unknown)."""
    if codec not in CODEC_IDS:
        raise CrashZipError(f"codec must be one of {list(CODEC_IDS)}")
    if chunk_size % 4:
        raise CrashZipError("chunk_size must be a multiple of 4")
    cid = CODEC_IDS[codec]
    workers = workers or os.cpu_count() or 1
    total = os.path.getsize(src)
    sha = hashlib.sha256()
    name = os.path.basename(src).encode("utf-8")[:65535]
    n_chunks = 0

    def chunks() -> Iterator[tuple]:
        with open(src, "rb") as f:
            while True:
                b = f.read(chunk_size)
                if not b:
                    return
                sha.update(b)
                yield (b, stride, cid, level)

    with open(dst, "wb") as out:
        out.write(_HDR.pack(MAGIC, VERSION, 0, chunk_size, stride, total, 0, b"\0" * 32, len(name)) + name)
        done = 0
        for tid, codec_used, raw_len, payload in _windowed_map(_encode_chunk, chunks(), workers):
            out.write(_CHK.pack(tid, codec_used, raw_len, len(payload)))
            out.write(payload)
            n_chunks += 1
            done += raw_len
            if progress:
                progress(done, total)
        out.seek(0)
        out.write(_HDR.pack(MAGIC, VERSION, 0, chunk_size, stride, total, n_chunks, sha.digest(), len(name)))
    csize = os.path.getsize(dst)
    return {"original": total, "compressed": csize, "ratio": (total / csize) if csize else 0.0,
            "chunks": n_chunks, "sha256": sha.hexdigest()}


def read_header(f: BinaryIO) -> dict:
    raw = f.read(_HDR.size)
    if len(raw) < _HDR.size:
        raise CrashZipError("file too short")
    magic, ver, _r, chunk, stride, size, n, sha, nl = _HDR.unpack(raw)
    if magic != MAGIC:
        raise CrashZipError("not a crashzip archive")
    if ver != VERSION:
        raise CrashZipError(f"unsupported version {ver}")
    name = f.read(nl).decode("utf-8", "replace")
    return {"chunk_size": chunk, "stride": stride, "size": size, "n_chunks": n,
            "sha256": sha.hex(), "name": name}


def decompress_file(src: str, dst: str, *, workers: int | None = None,
                    progress: Callable[[int, int], None] | None = None) -> dict:
    workers = workers or os.cpu_count() or 1
    with open(src, "rb") as f:
        h = read_header(f)

        def items() -> Iterator[tuple]:
            for _ in range(h["n_chunks"]):
                raw = f.read(_CHK.size)
                if len(raw) < _CHK.size:
                    raise CrashZipError("truncated archive")
                tid, codec, raw_len, clen = _CHK.unpack(raw)
                payload = f.read(clen)
                if len(payload) < clen:
                    raise CrashZipError("truncated archive")
                yield (tid, codec, raw_len, payload, h["stride"])

        sha = hashlib.sha256()
        written = 0
        tmp = dst + ".partial"
        try:
            with open(tmp, "wb") as out:
                for data in _windowed_map(_decode_chunk, items(), workers):
                    sha.update(data)
                    out.write(data)
                    written += len(data)
                    if progress:
                        progress(written, h["size"])
            if written != h["size"] or sha.hexdigest() != h["sha256"]:
                raise ChecksumError("SHA-256 mismatch: archive is corrupt, output discarded")
            os.replace(tmp, dst)
        finally:
            if os.path.exists(tmp):
                os.remove(tmp)
    return {"size": written, "sha256": sha.hexdigest(), "name": h["name"]}
