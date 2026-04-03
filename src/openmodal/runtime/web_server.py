"""Web server entrypoint — runs inside containers for @web_server functions.

Imports the user's module, calls the decorated serve() function,
then stays alive while the server subprocess runs.
"""

import asyncio
import importlib
import inspect
import os
import signal

module_name = os.environ["OPENMODAL_MODULE"]
function_name = os.environ["OPENMODAL_FUNCTION"]

module = importlib.import_module(module_name)
func = getattr(module, function_name)
raw = getattr(func, "__wrapped__", func)

if inspect.iscoroutinefunction(raw):
    asyncio.run(raw())
else:
    raw()

signal.pause()
