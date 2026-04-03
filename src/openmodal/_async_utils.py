"""Async/sync dual API — implements the .aio pattern from Modal."""

from __future__ import annotations

import asyncio
import functools
from typing import Any, Callable


class _AioWrapper:
    """Wraps a sync function so it can be awaited."""

    def __init__(self, fn: Callable):
        self._fn = fn

    async def __call__(self, *args: Any, **kwargs: Any) -> Any:
        return await asyncio.to_thread(self._fn, *args, **kwargs)


class _MethodWithAio:
    """Descriptor that adds .aio to a sync method.

    Usage:
        class Foo:
            @_method_with_aio
            def bar(self, x):
                return x * 2

        foo = Foo()
        foo.bar(3)            # sync: returns 6
        await foo.bar.aio(3)  # async: returns 6
    """

    def __init__(self, fn: Callable):
        self._fn = fn
        functools.update_wrapper(self, fn)

    def __set_name__(self, owner, name):
        self._name = name

    def __get__(self, obj, objtype=None):
        if obj is None:
            bound = self._fn
        else:
            bound = self._fn.__get__(obj, objtype)
        bound.aio = _AioWrapper(bound)
        return bound


class _StaticMethodWithAio:
    """Same as _MethodWithAio but for static/classmethods."""

    def __init__(self, fn: Callable):
        self._fn = fn

    def __set_name__(self, owner, name):
        self._name = name

    def __get__(self, obj, objtype=None):
        bound = self._fn
        bound.aio = _AioWrapper(bound)
        return bound


def method_with_aio(fn: Callable) -> _MethodWithAio:
    return _MethodWithAio(fn)


def static_with_aio(fn: Callable) -> _StaticMethodWithAio:
    return _StaticMethodWithAio(fn)
