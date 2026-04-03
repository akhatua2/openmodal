"""Console output with spinners and status updates."""

from __future__ import annotations

import itertools
import sys
import threading
import time


SPINNER_FRAMES = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"


class Spinner:
    def __init__(self, message: str):
        self._message = message
        self._start_time = time.time()
        self._running = False
        self._thread: threading.Thread | None = None

    def __enter__(self) -> Spinner:
        self._running = True
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._spin, daemon=True)
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._running = False
        if self._thread:
            self._thread.join()
        sys.stderr.write("\r\033[K")
        sys.stderr.flush()

    def update(self, message: str):
        self._message = message

    @property
    def elapsed(self) -> float:
        return time.time() - self._start_time

    def _spin(self):
        for frame in itertools.cycle(SPINNER_FRAMES):
            if not self._running:
                break
            elapsed = int(self.elapsed)
            suffix = f" ({elapsed}s)" if elapsed > 2 else ""
            sys.stderr.write(f"\r\033[K{frame} {self._message}{suffix}")
            sys.stderr.flush()
            time.sleep(0.1)


def success(message: str):
    sys.stderr.write(f"\r\033[K\u2713 {message}\n")
    sys.stderr.flush()


def fail(message: str):
    sys.stderr.write(f"\r\033[K\u2717 {message}\n")
    sys.stderr.flush()
