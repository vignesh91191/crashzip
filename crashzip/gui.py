"""Desktop application controller and entry point."""

from __future__ import annotations

import logging
import os
import queue
import threading
import tkinter as tk
from typing import Callable

from . import core
from .gui_view import CrashZipView
from .service import CompressionResult, CrashZipService, DecompressionResult

logger = logging.getLogger(__name__)


class CrashZipWindow:
    """Coordinates GUI events and CrashZip service operations."""

    def __init__(self, root: tk.Tk, service: CrashZipService | None = None) -> None:
        self.service = service or CrashZipService()
        self.view = CrashZipView(root, tuple(core.CODEC_IDS))
        self.events: queue.Queue = queue.Queue()
        self.busy = False

        self.view.bind_handlers(
            on_operation_changed=self._operation_changed,
            on_codec_changed=self._codec_changed,
            on_browse_input=self._browse_input,
            on_browse_output=self._browse_output,
            on_run=self._run,
            on_close=self._close,
        )
        self.view.after(100, self._poll_events)

    def _operation_changed(self, event=None) -> None:
        if event is not None and event.widget is not self.view.operation_box:
            return
        operation = self.view.operation
        self.view.set_operation_mode(operation)
        if operation == "Compress" and self.view.input_path:
            self.view.set_output_path(self.view.input_path + ".czip")
        elif operation == "Unzip":
            self._set_default_decompression_output()

    def _codec_changed(self, event=None) -> None:
        if event is not None and event.widget is not self.view.codec_box:
            return
        ranges = {"zstd": (1, 22), "xz": (0, 9), "brotli": (0, 11)}
        minimum, maximum = ranges[self.view.codec]
        try:
            level = int(self.view.level)
        except ValueError:
            level = minimum
        self.view.set_codec_level_range(minimum, maximum, level)

    def _browse_input(self) -> None:
        operation = self.view.operation
        if operation == "Compress":
            filetypes = (("All files", "*.*"),)
            title = "Choose file to compress"
        else:
            filetypes = (("CrashZip archives", "*.czip"), ("All files", "*.*"))
            title = (
                "Choose CrashZip archive to unzip"
                if operation == "Unzip"
                else "Choose CrashZip archive"
            )

        path = self.view.ask_input_file(title, filetypes)
        if not path:
            return
        self.view.set_input_path(path)
        if operation == "Compress":
            self.view.set_output_path(path + ".czip")
        elif operation == "Unzip":
            self._set_default_decompression_output()

    def _set_default_decompression_output(self) -> None:
        path = self.view.input_path
        if not path:
            self.view.set_output_path("")
            return
        try:
            name = self.service.get_info(path)["name"]
        except (OSError, core.CrashZipError) as error:
            self.view.set_output_path("")
            self.view.set_status(f"Could not read archive header: {error}")
            return
        filename = os.path.basename(name) or os.path.basename(path) + ".out"
        self.view.set_output_path(os.path.join(os.path.dirname(path), filename))

    def _browse_output(self) -> None:
        source = self.view.input_path
        current = self.view.output_path
        operation = self.view.operation
        path = self.view.ask_output_file(
            title="Choose restored file" if operation == "Unzip" else "Choose output file",
            initial_dir=os.path.dirname(current) if current else os.path.dirname(source),
            initial_file=os.path.basename(current) if current else "",
            extension=".czip" if operation == "Compress" else "",
            filetypes=(
                (("CrashZip archives", "*.czip"), ("All files", "*.*"))
                if operation == "Compress"
                else (("All files", "*.*"),)
            ),
        )
        if path:
            self.view.set_output_path(path)

    def _run(self) -> None:
        source = self.view.input_path.strip()
        if not source:
            self.view.show_warning("Input required", "Choose an input file first.")
            return

        operation = self.view.operation
        destination = self.view.output_path.strip()
        if operation != "Archive info" and not destination:
            if operation == "Compress":
                destination = source + ".czip"
            else:
                self._set_default_decompression_output()
                destination = self.view.output_path.strip()
            if not destination:
                return

        if destination and os.path.exists(destination) and not self.view.confirm_replace(
            destination
        ):
            return

        if operation == "Compress":
            try:
                level = int(self.view.level)
                stride = int(self.view.stride)
                if stride < 0:
                    raise ValueError("Stride cannot be negative.")
            except ValueError as error:
                self.view.show_error("Invalid option", str(error))
                return
            codec = self.view.codec
            verify = self.view.verify
            action = lambda: self.service.compress(
                source,
                destination,
                codec=codec,
                level=level,
                stride=stride,
                verify=verify,
                progress=self._report_progress,
            )
        elif operation == "Unzip":
            action = lambda: self.service.decompress(
                source, destination, progress=self._report_progress
            )
        else:
            action = lambda: self.service.get_info(source)

        self._set_busy(True)
        threading.Thread(
            target=self._execute, args=(action,), daemon=True, name="crashzip-worker"
        ).start()

    def _report_progress(self, completed: int, total: int) -> None:
        self.events.put(("progress", (completed, total)))

    def _execute(self, action: Callable[[], object]) -> None:
        try:
            result = action()
        except Exception as error:
            logger.exception("Desktop operation failed")
            self.events.put(("error", str(error)))
        else:
            self.events.put(("success", result))

    def _poll_events(self) -> None:
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "progress":
                    completed, total = payload
                    percentage = 100 * completed / total if total else 100
                    self.view.set_progress(percentage)
                    self.view.set_status(f"Processing... {percentage:.1f}%")
                elif event == "error":
                    self._set_busy(False)
                    self.view.set_status("Operation failed.")
                    self.view.show_error("CrashZip error", payload)
                else:
                    self._set_busy(False)
                    self._show_result(payload)
        except queue.Empty:
            pass
        self.view.after(100, self._poll_events)

    def _show_result(self, result) -> None:
        self.view.set_progress(100)
        if isinstance(result, CompressionResult):
            self.view.set_status(f"Compressed to {result.output_path}")
            verification = (
                "Passed: archive is bit-exact."
                if result.verified
                else "Not requested."
                if result.verified is None
                else "Failed."
            )
            text = (
                f"Output: {result.output_path}\n"
                f"Size: {result.original_size:,} -> {result.compressed_size:,} bytes "
                f"({result.ratio:.2f}x)\n"
                f"Verification: {verification}"
            )
            if result.verified is False:
                self.view.show_error("Verification failed", text)
            else:
                self.view.show_info("Compression complete", text)
        elif isinstance(result, DecompressionResult):
            self.view.set_status(f"Restored to {result.output_path}")
            self.view.show_info(
                "Unzip complete",
                f"Output: {result.output_path}\nSHA-256 verified.",
            )
        else:
            self.view.set_status("Archive information loaded.")
            details = "\n".join(f"{key}: {value}" for key, value in result.items())
            self.view.show_info("Archive info", details)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.view.set_busy(busy)

    def _close(self) -> None:
        if self.busy:
            self.view.show_warning(
                "Operation in progress", "Wait for the current operation to finish."
            )
            return
        self.view.close()


def main() -> None:
    root = tk.Tk()
    CrashZipWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
