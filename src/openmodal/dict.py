"""Dict — distributed key-value store backed by Redis."""

from __future__ import annotations

import pickle
from collections.abc import Iterator
from typing import Any


class Dict:
    """A distributed key-value store. Backed by a Redis hash.

    Usage::

        d = openmodal.Dict.from_name("my-dict")
        d["key"] = "value"
        print(d["key"])
    """

    def __init__(self, name: str):
        self.name = name
        from openmodal.redis_backend import _get_redis_client
        self._redis = _get_redis_client()

    @classmethod
    def from_name(cls, name: str, *, create_if_missing: bool = False) -> Dict:
        return cls(name)

    def __setitem__(self, key: str, value: Any):
        self._redis.hset(self.name, key, pickle.dumps(value))

    def __getitem__(self, key: str) -> Any:
        data = self._redis.hget(self.name, key)
        if data is None:
            raise KeyError(key)
        return pickle.loads(data)

    def __delitem__(self, key: str):
        if not self._redis.hdel(self.name, key):
            raise KeyError(key)

    def __contains__(self, key: str) -> bool:
        return self._redis.hexists(self.name, key)

    def __len__(self) -> int:
        return self._redis.hlen(self.name)

    def __iter__(self) -> Iterator[str]:
        return iter(self.keys())

    def get(self, key: str, default: Any = None) -> Any:
        data = self._redis.hget(self.name, key)
        if data is None:
            return default
        return pickle.loads(data)

    def pop(self, key: str, *args: Any) -> Any:
        data = self._redis.hget(self.name, key)
        if data is None:
            if args:
                return args[0]
            raise KeyError(key)
        self._redis.hdel(self.name, key)
        return pickle.loads(data)

    def keys(self) -> list[str]:
        return [k.decode() for k in self._redis.hkeys(self.name)]

    def values(self) -> list[Any]:
        return [pickle.loads(v) for v in self._redis.hvals(self.name)]

    def items(self) -> list[tuple[str, Any]]:
        raw = self._redis.hgetall(self.name)
        return [(k.decode(), pickle.loads(v)) for k, v in raw.items()]

    def update(self, mapping: dict[str, Any]):
        pipe = self._redis.pipeline()
        for k, v in mapping.items():
            pipe.hset(self.name, k, pickle.dumps(v))
        pipe.execute()

    def clear(self):
        self._redis.delete(self.name)
