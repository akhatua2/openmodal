"""OpenModal: Serverless GPU compute on GCP."""

from openmodal.app import App
from openmodal.function import FunctionSpec
from openmodal._decorators import concurrent, web_server
from openmodal.image import Image
from openmodal.secret import Secret
from openmodal.volume import Volume

__all__ = ["App", "FunctionSpec", "Image", "Secret", "Volume", "concurrent", "web_server"]
