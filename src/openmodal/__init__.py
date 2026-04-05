"""OpenModal — run Modal on your own cloud."""

from importlib.metadata import version as _v

__version__ = _v("openmodal")

from openmodal._decorators import concurrent, web_server
from openmodal.app import App
from openmodal.dict import Dict
from openmodal.function import FunctionSpec
from openmodal.image import Image
from openmodal.queue import Queue
from openmodal.sandbox import Sandbox
from openmodal.schedule import Cron, Period
from openmodal.secret import Secret
from openmodal.volume import Volume

__all__ = [
    "App", "Cron", "Dict", "FunctionSpec", "Image", "Period",
    "Queue", "Sandbox", "Secret", "Volume", "concurrent", "web_server",
]
