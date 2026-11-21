"""Application services for crashzip operations."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from typing import Callable

from . import core


@dataclass(frozen=True)
class CompressionResult:
    output_path: str
    original_size: int
    compressed_size: int
    ratio: float
    chunks: int
    sha256: str
    verified: bool | None


@dataclass(frozen=True)
class DecompressionResult:
    output_path: str
    size: int
    sha256: str


class CrashZipService:
    """Coordinates application workflows while core handles the file format."""

    def compress(
        self,
        input_path: str,
        output_path: str | None = None,
        *,
        codec: str = "zstd",
        level: int = 15,
        stride: int = 0,
        chunk_size: int = core.DEFAULT_CHUNK,
        workers: int | None = None,
        verify: bool = False,
        progress: Callable[[int, int], None] | None = None,
    ) -> CompressionResult:
        output_path = output_path or input_path + ".czip"
        self._ensure_distinct_paths(input_path, output_path)
        if chunk_size <= 0:
            raise core.CrashZipError("chunk_size must be greater than zero")
        if stride < 0:
            raise core.CrashZipError("stride cannot be negative")

        result = core.compress_file(
            input_path,
            output_path,
            codec=codec,
            level=level,
            stride=stride,
            chunk_size=chunk_size,
            workers=workers,
            progress=progress,
        )
        verified = None
        if verify:
            with tempfile.TemporaryDirectory() as temp_dir:
                verification_path = os.path.join(temp_dir, "verified-output")
                decompressed = core.decompress_file(
                    output_path, verification_path, workers=workers
                )
            verified = decompressed["sha256"] == result["sha256"]

        return CompressionResult(
            output_path=output_path,
            original_size=result["original"],
            compressed_size=result["compressed"],
            ratio=result["ratio"],
            chunks=result["chunks"],
            sha256=result["sha256"],
            verified=verified,
        )

    def decompress(
        self,
        input_path: str,
        output_path: str | None = None,
        *,
        workers: int | None = None,
        progress: Callable[[int, int], None] | None = None,
    ) -> DecompressionResult:
        if output_path is None:
            with open(input_path, "rb") as archive:
                name = core.read_header(archive)["name"]
            output_path = os.path.basename(name) or input_path + ".out"
        self._ensure_distinct_paths(input_path, output_path)

        result = core.decompress_file(
            input_path, output_path, workers=workers, progress=progress
        )
        return DecompressionResult(
            output_path=output_path,
            size=result["size"],
            sha256=result["sha256"],
        )

    @staticmethod
    def get_info(input_path: str) -> dict:
        with open(input_path, "rb") as archive:
            return core.read_header(archive)

    @staticmethod
    def _ensure_distinct_paths(input_path: str, output_path: str) -> None:
        source = os.path.normcase(os.path.abspath(input_path))
        destination = os.path.normcase(os.path.abspath(output_path))
        if source == destination:
            raise core.CrashZipError("input and output paths must be different")
