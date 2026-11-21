"""Compatibility exports for the compression engine."""

from .compression.engine import (
    CODEC_IDS,
    DEFAULT_CHUNK,
    MAGIC,
    VERSION,
    ChecksumError,
    CrashZipError,
    compress_file,
    decompress_file,
    read_header,
)

__all__ = [
    "CODEC_IDS",
    "DEFAULT_CHUNK",
    "MAGIC",
    "VERSION",
    "ChecksumError",
    "CrashZipError",
    "compress_file",
    "decompress_file",
    "read_header",
]
