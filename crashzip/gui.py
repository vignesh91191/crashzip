"""Cross-platform desktop interface for crashzip."""

from __future__ import annotations

import logging
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable

from . import core
from .service import CompressionResult, CrashZipService, DecompressionResult

logger = logging.getLogger(__name__)


class CrashZipWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.service = CrashZipService()
        self.events: queue.Queue = queue.Queue()
        self.busy = False

        root.title("CrashZip")
        root.minsize(560, 390)
        root.protocol("WM_DELETE_WINDOW", self._close)

        frame = ttk.Frame(root, padding=18)
        frame.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="CrashZip", font=("", 18, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 14)
        )

        ttk.Label(frame, text="Operation").grid(row=1, column=0, sticky="w", pady=5)
        self.operation = tk.StringVar(value="Compress")
        self.operation_box = ttk.Combobox(
            frame,
            textvariable=self.operation,
            values=("Compress", "Decompress", "Archive info"),
            state="readonly",
        )
        self.operation_box.grid(row=1, column=1, columnspan=2, sticky="ew", pady=5)
        self.operation_box.bind("<<ComboboxSelected>>", self._operation_changed)

        ttk.Label(frame, text="Input file").grid(row=2, column=0, sticky="w", pady=5)
        self.input_path = tk.StringVar()
        ttk.Entry(frame, textvariable=self.input_path).grid(
            row=2, column=1, sticky="ew", pady=5
        )
        self.input_button = ttk.Button(frame, text="Browse...", command=self._browse_input)
        self.input_button.grid(row=2, column=2, padx=(8, 0), pady=5)

        ttk.Label(frame, text="Output file").grid(row=3, column=0, sticky="w", pady=5)
        self.output_path = tk.StringVar()
        self.output_entry = ttk.Entry(frame, textvariable=self.output_path)
        self.output_entry.grid(row=3, column=1, sticky="ew", pady=5)
        self.output_button = ttk.Button(frame, text="Save as...", command=self._browse_output)
        self.output_button.grid(row=3, column=2, padx=(8, 0), pady=5)

        self.options = ttk.LabelFrame(frame, text="Compression options", padding=10)
        self.options.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(12, 8))
        self.options.columnconfigure(5, weight=1)

        ttk.Label(self.options, text="Codec").grid(row=0, column=0, sticky="w")
        self.codec = tk.StringVar(value="zstd")
        self.codec_box = ttk.Combobox(
            self.options,
            textvariable=self.codec,
            values=tuple(core.CODEC_IDS),
            state="readonly",
            width=10,
        )
        self.codec_box.grid(row=0, column=1, padx=(6, 14), sticky="w")
        self.codec_box.bind("<<ComboboxSelected>>", self._codec_changed)

        ttk.Label(self.options, text="Level").grid(row=0, column=2, sticky="w")
        self.level = tk.StringVar(value="15")
        self.level_box = ttk.Spinbox(
            self.options, from_=1, to=22, textvariable=self.level, width=5
        )
        self.level_box.grid(row=0, column=3, padx=(6, 14), sticky="w")

        ttk.Label(self.options, text="Stride (words)").grid(row=0, column=4, sticky="w")
        self.stride = tk.StringVar(value="0")
        ttk.Entry(self.options, textvariable=self.stride, width=9).grid(
            row=0, column=5, padx=(6, 12), sticky="w"
        )

        self.verify = tk.BooleanVar(value=True)
        self.verify_check = ttk.Checkbutton(
            self.options, text="Verify archive", variable=self.verify
        )
        self.verify_check.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.progress = ttk.Progressbar(frame, mode="determinate", maximum=100)
        self.progress.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(10, 4))

        self.status = tk.StringVar(value="Choose a file to get started.")
        ttk.Label(frame, textvariable=self.status, wraplength=520).grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(4, 10)
        )

        self.run_button = ttk.Button(frame, text="Run", command=self._run)
        self.run_button.grid(row=7, column=2, sticky="e")
        self._poll_events()

    def _operation_changed(self, _event=None) -> None:
        operation = self.operation.get()
        if operation == "Compress":
            self.options.grid()
            self.output_entry.state(["!disabled"])
            self.output_button.state(["!disabled"])
            if self.input_path.get():
                self.output_path.set(self.input_path.get() + ".czip")
        elif operation == "Decompress":
            self.options.grid_remove()
            self.output_entry.state(["!disabled"])
            self.output_button.state(["!disabled"])
            self._set_default_decompression_output()
        else:
            self.options.grid_remove()
            self.output_path.set("")
            self.output_entry.state(["disabled"])
            self.output_button.state(["disabled"])

    def _codec_changed(self, _event=None) -> None:
        ranges = {"zstd": (1, 22), "xz": (0, 9), "brotli": (0, 11)}
        minimum, maximum = ranges[self.codec.get()]
        self.level_box.configure(from_=minimum, to=maximum)
        try:
            level = int(self.level.get())
        except ValueError:
            level = minimum
        self.level.set(str(min(maximum, max(minimum, level))))

    def _browse_input(self) -> None:
        if self.operation.get() == "Compress":
            filetypes = (("All files", "*.*"),)
        else:
            filetypes = (("CrashZip archives", "*.czip"), ("All files", "*.*"))
        path = filedialog.askopenfilename(
            title="Choose input file", filetypes=filetypes
        )
        if path:
            self.input_path.set(path)
            if self.operation.get() == "Compress":
                self.output_path.set(path + ".czip")
            elif self.operation.get() == "Decompress":
                self._set_default_decompression_output()

    def _set_default_decompression_output(self) -> None:
        path = self.input_path.get()
        if not path:
            self.output_path.set("")
            return
        try:
            name = self.service.get_info(path)["name"]
        except (OSError, core.CrashZipError) as error:
            self.output_path.set("")
            self.status.set(f"Could not read archive header: {error}")
            return
        filename = os.path.basename(name) or os.path.basename(path) + ".out"
        self.output_path.set(os.path.join(os.path.dirname(path), filename))

    def _browse_output(self) -> None:
        source = self.input_path.get()
        current = self.output_path.get()
        filename = os.path.basename(current) if current else ""
        initial_dir = os.path.dirname(current) if current else os.path.dirname(source)
        path = filedialog.asksaveasfilename(
            title="Choose output file",
            initialdir=initial_dir or os.getcwd(),
            initialfile=filename,
            defaultextension=".czip" if self.operation.get() == "Compress" else "",
            filetypes=(
                (("CrashZip archives", "*.czip"), ("All files", "*.*"))
                if self.operation.get() == "Compress"
                else (("All files", "*.*"),)
            ),
        )
        if path:
            self.output_path.set(path)

    def _run(self) -> None:
        source = self.input_path.get().strip()
        if not source:
            messagebox.showwarning("Input required", "Choose an input file first.")
            return

        operation = self.operation.get()
        destination = self.output_path.get().strip()
        if operation != "Archive info" and not destination:
            if operation == "Compress":
                destination = source + ".czip"
            else:
                self._set_default_decompression_output()
                destination = self.output_path.get().strip()
            if not destination:
                return

        if destination and os.path.exists(destination) and not messagebox.askyesno(
            "Replace existing file?",
            f"The output already exists:\n{destination}\n\nReplace it?",
        ):
            return

        if operation == "Compress":
            try:
                level = int(self.level.get())
                stride = int(self.stride.get())
                if stride < 0:
                    raise ValueError("Stride cannot be negative.")
            except ValueError as error:
                messagebox.showerror("Invalid option", str(error))
                return
            codec = self.codec.get()
            verify = self.verify.get()
            action = lambda: self.service.compress(
                source,
                destination,
                codec=codec,
                level=level,
                stride=stride,
                verify=verify,
                progress=self._report_progress,
            )
        elif operation == "Decompress":
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
                    self.progress["value"] = 100 * completed / total if total else 100
                    self.status.set(f"Processing... {self.progress['value']:.1f}%")
                elif event == "error":
                    self._set_busy(False)
                    self.status.set("Operation failed.")
                    messagebox.showerror("CrashZip error", payload)
                else:
                    self._set_busy(False)
                    self._show_result(payload)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_events)

    def _show_result(self, result) -> None:
        self.progress["value"] = 100
        if isinstance(result, CompressionResult):
            self.status.set(f"Compressed to {result.output_path}")
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
                messagebox.showerror("Verification failed", text)
            else:
                messagebox.showinfo("Compression complete", text)
        elif isinstance(result, DecompressionResult):
            self.status.set(f"Restored to {result.output_path}")
            messagebox.showinfo(
                "Decompression complete",
                f"Output: {result.output_path}\nSHA-256 verified.",
            )
        else:
            self.status.set("Archive information loaded.")
            details = "\n".join(f"{key}: {value}" for key, value in result.items())
            messagebox.showinfo("Archive info", details)

    def _set_busy(self, busy: bool) -> None:
        self.busy = busy
        self.run_button.state(["disabled"] if busy else ["!disabled"])
        self.input_button.state(["disabled"] if busy else ["!disabled"])
        self.operation_box.state(["disabled"] if busy else ["!disabled"])
        self.codec_box.state(["disabled"] if busy else ["!disabled"])
        self.level_box.state(["disabled"] if busy else ["!disabled"])
        self.verify_check.state(["disabled"] if busy else ["!disabled"])
        self.status.set("Working..." if busy else "Ready.")
        if not busy:
            self.progress["value"] = 0

    def _close(self) -> None:
        if self.busy:
            messagebox.showwarning(
                "Operation in progress", "Wait for the current operation to finish."
            )
            return
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    CrashZipWindow(root)
    root.mainloop()


if __name__ == "__main__":
    main()
