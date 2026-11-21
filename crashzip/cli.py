"""crashzip command line interface."""

from __future__ import annotations

import argparse
import sys
import time

from . import core


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
            r = core.compress_file(a.input, out, codec=a.codec, level=a.level, stride=a.stride,
                                   chunk_size=a.chunk_mb * 1024 * 1024, workers=a.workers,
                                   progress=_bar("compress"))
            print(f"{r['original']:,} -> {r['compressed']:,} bytes  (ratio {r['ratio']:.2f}x)  -> {out}")
            if a.verify:
                import os, tempfile
                tmp = tempfile.mktemp(suffix=".verify")
                try:
                    v = core.decompress_file(out, tmp, workers=a.workers)
                finally:
                    if os.path.exists(tmp):
                        os.remove(tmp)
                ok = v["sha256"] == r["sha256"]
                print("verify:", "OK, bit-exact" if ok else "FAILED")
                return 0 if ok else 2
        elif a.cmd in ("d", "decompress"):
            out = a.output
            if not out:
                with open(a.input, "rb") as f:
                    out = core.read_header(f)["name"] or (a.input + ".out")
            r = core.decompress_file(a.input, out, workers=a.workers, progress=_bar("decompress"))
            print(f"restored {r['size']:,} bytes -> {out}  (sha256 verified)")
        else:
            with open(a.input, "rb") as f:
                h = core.read_header(f)
            for k, v in h.items():
                print(f"{k:11}: {v}")
    except core.CrashZipError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
