"""Generate a synthetic d3plot-like crash result file for testing.

Layout: header ints | initial coords | connectivity | N_STATES x
        [time | node coords (3N float32) | element vars (2E float32)]

Real solver output differs, but the statistical shape (smooth float32 fields
repeated per time state) is the same, so this is a fair stress test.
"""

import sys

import numpy as np


def main(path: str, nodes: int = 30000, elems: int = 25000, states: int = 40, seed: int = 7) -> None:
    rng = np.random.default_rng(seed)
    gx, gy = 150, nodes // 150
    xs, ys = np.meshgrid(np.linspace(0, 4.0, gx), np.linspace(0, 1.5, gy))
    x0 = np.stack([xs.ravel(), ys.ravel(), 0.1 * np.sin(3 * xs.ravel())], axis=1).astype(np.float32)
    n = len(x0)
    conn = rng.integers(0, n, size=(elems, 4), dtype=np.int32)
    with open(path, "wb") as f:
        f.write(np.arange(64, dtype=np.int32).tobytes())
        f.write(x0.tobytes())
        f.write(conn.tobytes())
        stress = rng.normal(200, 20, size=elems).astype(np.float32)
        pstrain = np.zeros(elems, dtype=np.float32)
        for k in range(states):
            t = np.float32(k * 0.002)
            crush = (1 - np.exp(-k / 8.0)) * 0.6
            ux = -crush * np.exp(-x0[:, 0] / 0.8)
            uz = 0.05 * crush * np.sin(6 * x0[:, 0] + 0.2 * k)
            disp = np.stack([ux, 0.02 * crush * x0[:, 1], uz], axis=1)
            coords = (x0 + disp + rng.normal(0, 1e-5, size=x0.shape)).astype(np.float32)
            stress = (stress * 0.995 + rng.normal(0, 0.8, size=elems)).astype(np.float32)
            pstrain = (pstrain + np.abs(rng.normal(0, 1e-3, size=elems))).astype(np.float32)
            f.write(t.tobytes())
            f.write(coords.tobytes())
            f.write(stress.tobytes())
            f.write(pstrain.tobytes())
    print(f"wrote {path}; state size = {1 + 3 * n + 2 * elems} words (use as --stride)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "sample_crash.d3plot")
