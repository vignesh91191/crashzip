import os
import tempfile
import unittest

from crashzip import CrashZipError
from crashzip.service import CrashZipService


class CrashZipServiceTests(unittest.TestCase):
    def setUp(self):
        self.service = CrashZipService()

    def test_compress_default_output_and_verify(self):
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "input.bin")
            with open(source, "wb") as file:
                file.write(b"crashzip service test" * 100)

            result = self.service.compress(source, verify=True, workers=1)

            self.assertEqual(result.output_path, source + ".czip")
            self.assertTrue(os.path.isfile(result.output_path))
            self.assertTrue(result.verified)

    def test_decompress_defaults_to_archived_file_name(self):
        with tempfile.TemporaryDirectory() as directory:
            original_directory = os.getcwd()
            try:
                os.chdir(directory)
                with open("input.bin", "wb") as file:
                    file.write(b"round trip")
                self.service.compress("input.bin", workers=1)

                result = self.service.decompress("input.bin.czip", workers=1)

                self.assertEqual(result.output_path, "input.bin")
                with open(result.output_path, "rb") as file:
                    self.assertEqual(file.read(), b"round trip")
            finally:
                os.chdir(original_directory)

    def test_rejects_same_input_and_output_path(self):
        with tempfile.TemporaryDirectory() as directory:
            source = os.path.join(directory, "input.bin")
            with open(source, "wb") as file:
                file.write(b"data")

            with self.assertRaises(CrashZipError):
                self.service.compress(source, source)


if __name__ == "__main__":
    unittest.main()
