"""Compare crashzip against plain general-purpose compressors on one file."""

import gzip
import lzma
import os
import sys
import tempfile
import time

import zstandard

from crashzip import compress_file


def main(path: str, stride: int) -> None:
    data = open(path, "rb").read()
    n = len(data)
    rows = []
    t = time.time(); r = len(gzip.compress(data, 9)); rows.append(("gzip -9", r, time.time() - t))
    t = time.time(); r = len(zstandard.ZstdCompressor(level=19).compress(data)); rows.append(("zstd -19 (plain)", r, time.time() - t))
    t = time.time(); r = len(lzma.compress(data, preset=6)); rows.append(("xz -6 (plain)", r, time.time() - t))
    with tempfile.TemporaryDirectory() as d:
        for label, kw in (("crashzip (auto transforms)", {}), (f"crashzip + stride={stride}", {"stride": stride})):
            t = time.time()
            r = compress_file(path, os.path.join(d, "x.czip"), **kw)["compressed"]
            rows.append((label, r, time.time() - t))
    print(f"original: {n:,} bytes")
    for name, size, sec in rows:
        print(f"{name:30} {size:>12,}  ratio {n / size:5.2f}x  {sec:6.1f}s")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]))
