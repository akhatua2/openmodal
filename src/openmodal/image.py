"""Image builder — chainable Dockerfile generation."""

from __future__ import annotations

import hashlib
import logging
import os
import shutil
import tempfile
from pathlib import Path

logger = logging.getLogger("openmodal.image")

OPENMODAL_PIP_INSTALL = "RUN pip install openmodal"

class Image:
    """Chainable builder that produces a Dockerfile and pushes to Artifact Registry."""

    def __init__(self, commands: list[str] | None = None, context_files: dict[str, str] | None = None):
        self._commands: list[str] = commands or []
        self._context_files: dict[str, str] = context_files or {}

    def _append(self, *lines: str, **extra_files: str) -> Image:
        new_files = {**self._context_files, **extra_files}
        return Image(self._commands + list(lines), new_files)

    @classmethod
    def from_dockerfile(cls, path: str, *, context_dir: str | None = None) -> Image:
        dockerfile_content = Path(path).read_text()
        img = cls(dockerfile_content.strip().split("\n"))
        if context_dir:
            for f in Path(context_dir).iterdir():
                if f.is_file() and f.name != "Dockerfile":
                    img._context_files[f.name] = str(f)
        return img

    @classmethod
    def from_registry(cls, tag: str, *, add_python: str | None = None, secret: any = None) -> Image:
        img = cls([f"FROM {tag}", "ENV DEBIAN_FRONTEND=noninteractive"])
        if add_python:
            img = img._append(
                "RUN apt-get update && apt-get install -y python3 python3-pip python3-venv && "
                "ln -sf /usr/bin/python3 /usr/bin/python && "
                "rm -f /usr/lib/python*/EXTERNALLY-MANAGED && "
                "rm -rf /var/lib/apt/lists/*",
            )
        return img

    @classmethod
    def debian_slim(cls, python_version: str = "3.12") -> Image:
        return cls.from_registry("ubuntu:24.04", add_python=python_version)

    def entrypoint(self, args: list[str]) -> Image:
        if not args:
            return self._append("ENTRYPOINT []")
        joined = ", ".join(f'"{a}"' for a in args)
        return self._append(f"ENTRYPOINT [{joined}]")

    def apt_install(self, *packages: str) -> Image:
        pkgs = " ".join(packages)
        return self._append(
            f"RUN apt-get update && apt-get install -y {pkgs} && rm -rf /var/lib/apt/lists/*"
        )

    def pip_install(self, *packages: str, extra_options: str = "") -> Image:
        pkgs = " ".join(f'"{p}"' for p in packages)
        return self._append(f"RUN pip install {extra_options} {pkgs}".strip())

    def uv_pip_install(self, *packages: str, extra_options: str = "") -> Image:
        img = self._append(
            "COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv"
        )
        pkgs = " ".join(f'"{p}"' for p in packages)
        return img._append(
            f"RUN /usr/local/bin/uv pip install --python $(command -v python) "
            f"--compile-bytecode {extra_options} {pkgs}".strip()
        )

    def env(self, vars: dict[str, str]) -> Image:
        return self._append(*(f"ENV {k}={v}" for k, v in vars.items()))

    def run_commands(self, *commands: str) -> Image:
        return self._append(*(f"RUN {cmd}" for cmd in commands))

    def workdir(self, path: str) -> Image:
        return self._append(f"WORKDIR {path}")

    def with_web_server(self, source_file: str, function_name: str) -> Image:
        """Extend this image to run a @web_server function on startup."""
        filename = os.path.basename(source_file)
        module_name = filename.removesuffix(".py")
        img = self._append(
            OPENMODAL_PIP_INSTALL,
            f"COPY {filename} /opt/{filename}",
            "ENV PYTHONPATH=/opt",
            f"ENV OPENMODAL_MODULE={module_name}",
            f"ENV OPENMODAL_FUNCTION={function_name}",
            'CMD ["python", "-m", "openmodal.runtime.web_server"]',
        )
        img._context_files[filename] = source_file
        return img

    def with_agent(self, port: int = 50051, source_file: str | None = None) -> Image:
        """Extend this image with the openmodal SDK, execution agent, and user source."""
        img = self._append(
            OPENMODAL_PIP_INSTALL,
            "ENV PYTHONPATH=/opt",
        )
        if source_file and os.path.isfile(source_file):
            filename = os.path.basename(source_file)
            img = img._append(f"COPY {filename} /opt/{filename}")
            img._context_files[filename] = source_file
        return img._append(f'CMD ["python", "-m", "openmodal.runtime.agent"]')

    def to_dockerfile(self) -> str:
        return "\n".join(self._commands) + "\n"

    def content_hash(self) -> str:
        h = hashlib.sha256(self.to_dockerfile().encode())
        for name in sorted(self._context_files):
            src = self._context_files[name]
            if os.path.isfile(src):
                h.update(Path(src).read_bytes())
        return h.hexdigest()[:12]

    def _prepare_build_context(self, tmpdir: str):
        (Path(tmpdir) / "Dockerfile").write_text(self.to_dockerfile())
        for dest_name, src_path in self._context_files.items():
            shutil.copy2(src_path, Path(tmpdir) / dest_name)

    def build_and_push(self, name: str, *, use_cloud_build: bool = True, provider=None) -> str:
        """Build and push to registry. Returns the full image URI."""
        if provider is None:
            from openmodal.providers import get_provider
            provider = get_provider()

        tag = self.content_hash()

        with tempfile.TemporaryDirectory() as tmpdir:
            self._prepare_build_context(tmpdir)
            image_uri = provider.build_image(tmpdir, name, tag)

        logger.debug(f"Built and pushed: {image_uri}")
        return image_uri
