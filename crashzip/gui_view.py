"""Tkinter widgets and presentation for the desktop application."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from typing import Callable


class CrashZipView:
    def __init__(self, root: tk.Tk, codecs: tuple[str, ...]) -> None:
        self.root = root

        root.title("CrashZip")
        root.minsize(560, 390)

        frame = ttk.Frame(root, padding=18)
        frame.grid(sticky="nsew")
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="CrashZip", font=("", 18, "bold")).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 14)
        )

        ttk.Label(frame, text="Operation").grid(row=1, column=0, sticky="w", pady=5)
        self._operation = tk.StringVar(value="Compress")
        self.operation_box = ttk.Combobox(
            frame,
            textvariable=self._operation,
            values=("Compress", "Unzip", "Archive info"),
            state="readonly",
        )
        self.operation_box.grid(row=1, column=1, columnspan=2, sticky="ew", pady=5)

        ttk.Label(frame, text="Input file").grid(row=2, column=0, sticky="w", pady=5)
        self._input_path = tk.StringVar()
        self.input_entry = ttk.Entry(frame, textvariable=self._input_path)
        self.input_entry.grid(row=2, column=1, sticky="ew", pady=5)
        self.input_button = ttk.Button(frame, text="Browse...")
        self.input_button.grid(row=2, column=2, padx=(8, 0), pady=5)

        ttk.Label(frame, text="Output file").grid(row=3, column=0, sticky="w", pady=5)
        self._output_path = tk.StringVar()
        self.output_entry = ttk.Entry(frame, textvariable=self._output_path)
        self.output_entry.grid(row=3, column=1, sticky="ew", pady=5)
        self.output_button = ttk.Button(frame, text="Save as...")
        self.output_button.grid(row=3, column=2, padx=(8, 0), pady=5)

        self.options = ttk.LabelFrame(frame, text="Compression options", padding=10)
        self.options.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(12, 8))
        self.options.columnconfigure(5, weight=1)

        ttk.Label(self.options, text="Codec").grid(row=0, column=0, sticky="w")
        self._codec = tk.StringVar(value="zstd")
        self.codec_box = ttk.Combobox(
            self.options,
            textvariable=self._codec,
            values=codecs,
            state="readonly",
            width=10,
        )
        self.codec_box.grid(row=0, column=1, padx=(6, 14), sticky="w")

        ttk.Label(self.options, text="Level").grid(row=0, column=2, sticky="w")
        self._level = tk.StringVar(value="15")
        self.level_box = ttk.Spinbox(
            self.options, from_=1, to=22, textvariable=self._level, width=5
        )
        self.level_box.grid(row=0, column=3, padx=(6, 14), sticky="w")

        ttk.Label(self.options, text="Stride (words)").grid(row=0, column=4, sticky="w")
        self._stride = tk.StringVar(value="0")
        self.stride_entry = ttk.Entry(self.options, textvariable=self._stride, width=9)
        self.stride_entry.grid(row=0, column=5, padx=(6, 12), sticky="w")

        self._verify = tk.BooleanVar(value=True)
        self.verify_check = ttk.Checkbutton(
            self.options, text="Verify archive", variable=self._verify
        )
        self.verify_check.grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.progress = ttk.Progressbar(frame, mode="determinate", maximum=100)
        self.progress.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(10, 4))

        self._status = tk.StringVar(value="Choose a file to get started.")
        ttk.Label(frame, textvariable=self._status, wraplength=520).grid(
            row=6, column=0, columnspan=3, sticky="w", pady=(4, 10)
        )

        self.run_button = ttk.Button(frame, text="Compress")
        self.run_button.grid(row=7, column=2, sticky="e")
        self.set_operation_mode("Compress")

    def bind_handlers(
        self,
        *,
        on_operation_changed: Callable,
        on_codec_changed: Callable,
        on_browse_input: Callable,
        on_browse_output: Callable,
        on_run: Callable,
        on_close: Callable,
    ) -> None:
        self.operation_box.bind("<<ComboboxSelected>>", on_operation_changed)
        self.codec_box.bind("<<ComboboxSelected>>", on_codec_changed)
        self.input_button.configure(command=on_browse_input)
        self.output_button.configure(command=on_browse_output)
        self.run_button.configure(command=on_run)
        self.root.protocol("WM_DELETE_WINDOW", on_close)

    @property
    def operation(self) -> str:
        return self._operation.get()

    @property
    def input_path(self) -> str:
        return self._input_path.get()

    @property
    def output_path(self) -> str:
        return self._output_path.get()

    @property
    def codec(self) -> str:
        return self._codec.get()

    @property
    def level(self) -> str:
        return self._level.get()

    @property
    def stride(self) -> str:
        return self._stride.get()

    @property
    def verify(self) -> bool:
        return self._verify.get()

    def set_input_path(self, path: str) -> None:
        self._input_path.set(path)

    def set_output_path(self, path: str) -> None:
        self._output_path.set(path)

    def set_status(self, text: str) -> None:
        self._status.set(text)

    def set_progress(self, value: float) -> None:
        self.progress["value"] = value

    def set_operation_mode(self, operation: str) -> None:
        compression_controls = (
            self.codec_box,
            self.level_box,
            self.stride_entry,
            self.verify_check,
        )
        for control in compression_controls:
            control.state(
                ["!disabled"] if operation == "Compress" else ["disabled"]
            )

        if operation == "Compress":
            self.run_button.configure(text="Compress")
            self.options.grid()
            self.output_entry.state(["!disabled"])
            self.output_button.state(["!disabled"])
        elif operation == "Unzip":
            self.run_button.configure(text="Unzip")
            self.options.grid_remove()
            self.output_entry.state(["!disabled"])
            self.output_button.state(["!disabled"])
        else:
            self.run_button.configure(text="Show info")
            self.options.grid_remove()
            self.set_output_path("")
            self.output_entry.state(["disabled"])
            self.output_button.state(["disabled"])

    def set_codec_level_range(self, minimum: int, maximum: int, level: int) -> None:
        self.level_box.configure(from_=minimum, to=maximum)
        self._level.set(str(min(maximum, max(minimum, level))))

    def set_busy(self, busy: bool) -> None:
        controls = (
            self.run_button,
            self.operation_box,
            self.input_entry,
            self.input_button,
            self.output_entry,
            self.output_button,
            self.codec_box,
            self.level_box,
            self.stride_entry,
            self.verify_check,
        )
        for control in controls:
            control.state(["disabled"] if busy else ["!disabled"])

        if not busy:
            if self.operation == "Archive info":
                self.output_entry.state(["disabled"])
                self.output_button.state(["disabled"])
            self.set_status("Ready.")
            self.set_progress(0)
        else:
            self.set_status("Working...")

    def ask_input_file(self, title: str, filetypes: tuple) -> str:
        return filedialog.askopenfilename(title=title, filetypes=filetypes)

    def ask_output_file(
        self,
        *,
        title: str,
        initial_dir: str,
        initial_file: str,
        extension: str,
        filetypes: tuple,
    ) -> str:
        return filedialog.asksaveasfilename(
            title=title,
            initialdir=initial_dir or os.getcwd(),
            initialfile=initial_file,
            defaultextension=extension,
            filetypes=filetypes,
        )

    def confirm_replace(self, path: str) -> bool:
        return messagebox.askyesno(
            "Replace existing file?",
            f"The output already exists:\n{path}\n\nReplace it?",
        )

    @staticmethod
    def show_warning(title: str, text: str) -> None:
        messagebox.showwarning(title, text)

    @staticmethod
    def show_error(title: str, text: str) -> None:
        messagebox.showerror(title, text)

    @staticmethod
    def show_info(title: str, text: str) -> None:
        messagebox.showinfo(title, text)

    def after(self, milliseconds: int, callback: Callable) -> None:
        self.root.after(milliseconds, callback)

    def close(self) -> None:
        self.root.destroy()
