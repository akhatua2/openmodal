"""Cron runner entrypoint -- runs inside CronJob pods.

Imports the user's module, calls the scheduled function, then exits.
"""

import asyncio
import importlib
import inspect
import logging
import os
import sys

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("openmodal.cron_runner")

module_name = os.environ["OPENMODAL_MODULE"]
function_name = os.environ["OPENMODAL_FUNCTION"]

logger.info(f"Cron trigger: {module_name}.{function_name}")

module = importlib.import_module(module_name)
func = getattr(module, function_name)
raw = getattr(func, "__wrapped__", func)

try:
    if inspect.iscoroutinefunction(raw):
        asyncio.run(raw())
    else:
        raw()
    logger.info("Cron job completed successfully.")
except Exception:
    logger.exception("Cron job failed.")
    sys.exit(1)
