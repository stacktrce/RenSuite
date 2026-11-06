"""Shared GUI helpers: background tasks, progress panel, small utilities."""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import traceback
import tkinter as tk
from tkinter import messagebox, ttk

from ..i18n import t
from .theme import c


class TaskRunner:
    """Runs work on a background thread and marshals results to the Tk thread."""

    def __init__(self, root: tk.Misc):
        self.root = root
        self._queue = queue.Queue()
        self._poll()

    def _poll(self):
        while True:
            try:
                fn = self._queue.get_nowait()
            except queue.Empty:
                break
            try:
                fn()
            except tk.TclError:
                pass  # the widget was destroyed meanwhile (e.g. the UI was rebuilt)
        self.root.after(40, self._poll)

    def call(self, fn):
        """Schedule ``fn`` on the Tk thread (safe from any thread)."""
        self._queue.put(fn)

    def run(self, work, on_done=None, on_error=None):
        def target():
            try:
                result = work()
            except Exception as exc:
                traceback.print_exc()
                handler = on_error or (lambda e: messagebox.showerror(t("error"), str(e)))
                self.call(lambda e=exc: handler(e))
            else:
                if on_done:
                    self.call(lambda: on_done(result))

        threading.Thread(target=target, daemon=True).start()


class ProgressPanel(ttk.Frame):
    """Status text, progress bar and cancel button for one long operation."""

    def __init__(self, master, runner: TaskRunner):
        super().__init__(master)
        self.runner = runner
        self.cancel_event = threading.Event()
        self.label = ttk.Label(self, text="", foreground=c("gray"))
        self.label.pack(fill=tk.X)
        row = ttk.Frame(self)
        row.pack(fill=tk.X, pady=(2, 0))
        self.bar = ttk.Progressbar(row, mode="determinate")
        self.bar.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.cancel_btn = ttk.Button(row, text=t("cancel"), command=self.cancel_event.set, state=tk.DISABLED)
        self.cancel_btn.pack(side=tk.RIGHT, padx=(6, 0))
        self.busy = False

    def start(self, text=""):
        self.busy = True
        self.cancel_event.clear()
        self.cancel_btn.config(state=tk.NORMAL)
        self.set_status(text)
        self.bar.config(value=0, maximum=1)

    def progress(self, prefix: str):
        """A thread-safe ``progress(done, total, name)`` callback."""
        def cb(done, total, name):
            self.runner.call(lambda: self._update(done, total, prefix, name))
        return cb

    def _update(self, done, total, prefix, name):
        self.bar.config(maximum=max(total, 1), value=done)
        self.label.config(text=("%s — %s" % (prefix, name)) if name else prefix, foreground="")

    def finish(self, text="", color="green"):
        self.busy = False
        self.cancel_btn.config(state=tk.DISABLED)
        if self.cancel_event.is_set():
            text, color = t("cancelled"), "orange"
        self.set_status(text, color)

    def set_status(self, text, color="gray"):
        self.label.config(text=text, foreground=c(color))


def open_path(path):
    path = str(path)
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 - opens a folder in Explorer
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024.0
    return str(n)


def scrolled(master, widget_cls, **kwargs):
    """Create ``widget_cls`` inside a frame with vertical (and horizontal) scrollbars."""
    frame = ttk.Frame(master)
    widget = widget_cls(frame, **kwargs)
    ys = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=widget.yview)
    xs = ttk.Scrollbar(frame, orient=tk.HORIZONTAL, command=widget.xview)
    widget.configure(yscrollcommand=ys.set, xscrollcommand=xs.set)
    widget.grid(row=0, column=0, sticky="nsew")
    ys.grid(row=0, column=1, sticky="ns")
    xs.grid(row=1, column=0, sticky="ew")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    return frame, widget
