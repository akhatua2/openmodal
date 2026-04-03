"""ContainerProcess — matches Modal's process API for sandbox exec results."""

from __future__ import annotations

from openmodal._async_utils import _AioWrapper


class _StreamReader:
    def __init__(self, data: str):
        self._data = data
        self.read = self._make_read()

    def _make_read(self):
        def read():
            return self._data
        read.aio = _AioWrapper(read)
        return read


class ContainerProcess:
    def __init__(self, stdout_data: str, stderr_data: str, returncode: int):
        self.stdout = _StreamReader(stdout_data)
        self.stderr = _StreamReader(stderr_data)
        self._returncode = returncode
        self.wait = self._make_wait()

    def _make_wait(self):
        def wait():
            return self._returncode
        wait.aio = _AioWrapper(wait)
        return wait
