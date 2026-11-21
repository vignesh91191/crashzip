"""crashzip command line interface."""

from __future__ import annotations

import argparse
import sys
import time

from . import core
from .service import CrashZipService


def _bar(label: str):
    last = [0.0]

    def cb(done: int, total: int) -> None:
        now = time.time()
        if now - last[0] > 0.2 or done >= total:
            last[0] = now
            pct = 100 * done / total if total else 100
            sys.stderr.write(f"\r{label} {pct:5.1f}%")
            sys.stderr.flush()
            if done >= total:
                sys.stderr.write("\n")

    return cb


def main(argv=None) -> int:
    service = CrashZipService()
    p = argparse.ArgumentParser(prog="crashzip",
                                description="Lossless compressor for crash-simulation result files.")
    sub = p.add_subparsers(dest="cmd", required=True)

    c = sub.add_parser("c", aliases=["compress"], help="compress a file")
    c.add_argument("input")
    c.add_argument("-o", "--output")
    c.add_argument("-l", "--level", type=int, default=15, help="codec level (zstd 1-22, xz 0-9, brotli 0-11)")
    c.add_argument("--codec", choices=list(core.CODEC_IDS), default="zstd")
    c.add_argument("--stride", type=int, default=0,
                   help="size of ONE time state in 32-bit words; enables delta against the previous state")
    c.add_argument("--chunk-mb", type=int, default=8)
    c.add_argument("-j", "--workers", type=int, default=None)
    c.add_argument("--verify", action="store_true", help="decompress after compressing and compare hashes")

    d = sub.add_parser("d", aliases=["decompress"], help="restore the original file")
    d.add_argument("input")
    d.add_argument("-o", "--output")
    d.add_argument("-j", "--workers", type=int, default=None)

    i = sub.add_parser("info", help="show archive header")
    i.add_argument("input")

    a = p.parse_args(argv)

    try:
        if a.cmd in ("c", "compress"):
            out = a.output or a.input + ".czip"
            r = service.compress(
                a.input,
                out,
                codec=a.codec,
                level=a.level,
                stride=a.stride,
                chunk_size=a.chunk_mb * 1024 * 1024,
                workers=a.workers,
                verify=a.verify,
                progress=_bar("compress"),
            )
            print(f"{r.original_size:,} -> {r.compressed_size:,} bytes  "
                  f"(ratio {r.ratio:.2f}x)  -> {r.output_path}")
            if r.verified is not None:
                print("verify:", "OK, bit-exact" if r.verified else "FAILED")
                return 0 if r.verified else 2
        elif a.cmd in ("d", "decompress"):
            r = service.decompress(
                a.input, a.output, workers=a.workers, progress=_bar("decompress")
            )
            print(f"restored {r.size:,} bytes -> {r.output_path}  (sha256 verified)")
        else:
            h = service.get_info(a.input)
            for k, v in h.items():
                print(f"{k:11}: {v}")
    except core.CrashZipError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
