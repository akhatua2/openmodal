"""Queue — distributed FIFO queue backed by Redis."""

from __future__ import annotations

import pickle
from typing import Any


class Queue:
    """A distributed FIFO queue. Backed by a Redis list.

    Usage::

        q = openmodal.Queue.from_name("work")
        q.put("item")
        item = q.get()
    """

    def __init__(self, name: str):
        self.name = name
        from openmodal.redis_backend import _get_redis_client
        self._redis = _get_redis_client()

    @classmethod
    def from_name(cls, name: str, *, create_if_missing: bool = False) -> Queue:
        return cls(name)

    def put(self, value: Any):
        """Add an item to the end of the queue."""
        self._redis.rpush(self.name, pickle.dumps(value))

    def put_many(self, values: list[Any]):
        """Add multiple items to the end of the queue."""
        pipe = self._redis.pipeline()
        for v in values:
            pipe.rpush(self.name, pickle.dumps(v))
        pipe.execute()

    def get(self, *, timeout: float = 0) -> Any:
        """Remove and return an item from the front of the queue.

        If timeout > 0, blocks up to that many seconds waiting for an item.
        If timeout == 0, returns immediately (raises Empty if nothing available).
        """
        if timeout > 0:
            result = self._redis.blpop(self.name, timeout=int(timeout))
            if result is None:
                raise TimeoutError(f"Queue '{self.name}' get() timed out after {timeout}s")
            return pickle.loads(result[1])
        data = self._redis.lpop(self.name)
        if data is None:
            raise Empty(f"Queue '{self.name}' is empty")
        return pickle.loads(data)

    def get_many(self, n: int) -> list[Any]:
        """Remove and return up to n items from the front of the queue."""
        pipe = self._redis.pipeline()
        for _ in range(n):
            pipe.lpop(self.name)
        results = pipe.execute()
        return [pickle.loads(data) for data in results if data is not None]

    def __len__(self) -> int:
        return self._redis.llen(self.name)

    def empty(self) -> bool:
        return len(self) == 0

    def clear(self):
        self._redis.delete(self.name)


class Empty(Exception):
    """Raised when get() is called on an empty queue with no timeout."""
