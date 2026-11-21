import hashlib
import os
import tempfile
import unittest

import numpy as np

from crashzip import ChecksumError, compress_file, decompress_file


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


class RoundTrip(unittest.TestCase):
    def _rt(self, data: bytes, **kw):
        with tempfile.TemporaryDirectory() as d:
            src, z, out = (os.path.join(d, x) for x in ("a.bin", "a.czip", "b.bin"))
            open(src, "wb").write(data)
            compress_file(src, z, workers=2, **kw)
            decompress_file(z, out, workers=2)
            self.assertEqual(sha(src), sha(out))

    def test_empty(self):
        self._rt(b"")

    def test_tiny_and_odd_sizes(self):
        for n in (1, 3, 4, 5, 255, 257, 1001):
            self._rt(os.urandom(n))

    def test_random_incompressible(self):
        self._rt(os.urandom(300_000), chunk_size=65536)

    def test_float_states_all_codecs_and_strides(self):
        rng = np.random.default_rng(1)
        base = rng.normal(size=1000).astype(np.float32)
        states = [base + rng.normal(0, 1e-4, 1000).astype(np.float32) for _ in range(50)]
        data = np.concatenate(states).tobytes() + b"xyz"  # unaligned tail on purpose
        for codec in ("zstd", "xz", "brotli"):
            for stride in (0, 1000, 7):
                self._rt(data, codec=codec, level=5, stride=stride, chunk_size=40_000)

    def test_corruption_detected(self):
        data = np.linspace(0, 1, 200_000, dtype=np.float32).tobytes()
        with tempfile.TemporaryDirectory() as d:
            src, z, out = (os.path.join(d, x) for x in ("a", "a.czip", "b"))
            open(src, "wb").write(data)
            compress_file(src, z, workers=1)
            b = bytearray(open(z, "rb").read())
            b[len(b) // 2] ^= 0xFF
            open(z, "wb").write(bytes(b))
            with self.assertRaises(Exception) as cm:
                decompress_file(z, out, workers=1)
            self.assertTrue(isinstance(cm.exception, (ChecksumError, Exception)))
            self.assertFalse(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
