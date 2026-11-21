# crashzip

A compressor for crash-simulation result files (LS-DYNA d3plot, Radioss,
PAM-CRASH, or any binary dominated by float32 arrays), built only on open-source parts:
**zstd**, **LZMA/xz** and **brotli**, plus NumPy for the float-aware transforms.

Compression is **lossless**: unzip gives back a bit-identical file, and every archive
stores a SHA-256 that is checked on decompress (a corrupt archive is rejected and no
output file is left behind).

## Install

    pip install numpy zstandard          # required
    pip install brotli                   # optional codec
    pip install .                        # optional: gives the `crashzip` command

Without installing, run from this folder with `python -m crashzip ...`.

## Desktop app

Install the package, then launch the cross-platform desktop interface:

    pip install .
    crashzip-app

You can also run it from the source folder with `python -m crashzip.gui`.
The interface uses Tkinter; some Linux distributions require installing their
system Tk package (for example, `python3-tk`) separately.
It supports compression, unzipping/restoring `.czip` archives, and archive info.

## Use

    # compress (writes model.d3plot.czip)
    python -m crashzip c model.d3plot --stride 140001 --verify

    # restore the original file
    python -m crashzip d model.d3plot.czip -o model_restored.d3plot

    # show header
    python -m crashzip info model.d3plot.czip

Options for `c`: `--codec zstd|xz|brotli`, `-l LEVEL`, `--chunk-mb N`, `-j WORKERS`,
`--verify` (round-trips the archive and compares hashes).

## Application structure

`crashzip.core` implements the archive format and compression algorithms.
`crashzip.service.CrashZipService` coordinates compression, decompression, and
verification workflows. The desktop controller handles interactions and
operation flow, while `crashzip.gui_view` owns the Tkinter widgets and display.
The CLI handles argument parsing and terminal output.
The service is also available to Python callers:

    from crashzip import CrashZipService

    result = CrashZipService().compress("model.d3plot", verify=True)
    print(result.output_path, result.verified)

### The `--stride` option (matters a lot)

Solver files store the same fields once per time state, so the best predictor of a value
is the same value one state earlier. Pass the size of **one state in 32-bit words** and
crashzip XORs each word with its counterpart in the previous state, which zeroes the bits
that did not change. For a file with `S` states and a header of `H` words:
`stride = (total_words - H) / S`. Without it, crashzip still tries shuffle and
neighbour-delta transforms and keeps whichever is smallest per chunk.

## How it works

1. File is split into 8 MiB chunks, compressed in parallel (bounded memory).
2. Per chunk, a fast trial picks the best transform: none, byte-plane shuffle,
   XOR-delta (stride 1), or XOR-delta (stride = one state) + shuffle.
3. The chosen layout goes through zstd (default level 15), xz or brotli.
   Incompressible chunks are stored raw.

## Test and benchmark

    python -m unittest tests.test_roundtrip -v
    python tools/gen_sample.py sample.d3plot        # synthetic crash file
    PYTHONPATH=. python tools/bench.py sample.d3plot 140001

Sample result on a 23 MB synthetic file: gzip -9 1.30x, plain zstd -19 1.45x,
plain xz 1.73x, crashzip 1.46x (auto) and 1.76x (with stride), all bit-exact.

## Limits and next steps

* Lossless ratios on real float32 solver output are modest (often 1.5x to 3x) because
  the low mantissa bits are close to noise. Larger ratios can be achieved with **lossy
  quantization and a user-set error bound**; that mode is not included yet.
* No d3plot parser yet: geometry, connectivity and result states are treated as one
  byte stream. Splitting by field type would improve ratios further.
