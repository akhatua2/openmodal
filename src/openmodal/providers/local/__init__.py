"""Local Docker provider — runs everything on localhost using Docker."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from openmodal.function import FunctionSpec
from openmodal.providers.base import CloudProvider

logger = logging.getLogger("openmodal.local")

LABEL = "managed-by=openmodal"
VOLUMES_DIR = Path.home() / ".openmodal" / "volumes"


def _has_nvidia_gpu() -> bool:
    """Check if the NVIDIA Docker runtime is available."""
    result = subprocess.run(
        ["docker", "info", "--format", "{{.Runtimes}}"],
        capture_output=True, text=True,
    )
    return "nvidia" in result.stdout.lower() or "gpu" in result.stdout.lower()


def _get_local_gpus() -> list[str]:
    """Return list of GPU model names on this machine via nvidia-smi."""
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    return [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]


def _check_gpu(requested: str):
    """Validate that the requested GPU type is available locally."""
    if not _has_nvidia_gpu():
        raise RuntimeError(
            f"This machine doesn't have a {requested} (wouldn't that be nice :P). "
            f"Remove --local to run on cloud GPUs."
        )
    local_gpus = _get_local_gpus()
    if not local_gpus:
        return  # can't detect, let Docker handle it
    # Check if the requested type matches any local GPU (case-insensitive substring)
    req = requested.lower()
    if not any(req in gpu.lower() for gpu in local_gpus):
        raise RuntimeError(
            f"You asked for a {requested} but this machine has: {', '.join(local_gpus)}. "
            f"Close, but no cigar :P Remove --local to run on cloud GPUs."
        )


class LocalProvider(CloudProvider):

    def preflight_check(self, spec):
        result = subprocess.run(["docker", "info"], capture_output=True)
        if result.returncode != 0:
            raise RuntimeError("Docker is not running. Start Docker and try again.")
        if spec.gpu:
            _check_gpu(spec.gpu)

    def _ensure_default_agent_image(self, source_file: str | None = None) -> str:
        from openmodal.image import OPENMODAL_PIP_INSTALL, Image
        img = Image.debian_slim()
        img = img._append(OPENMODAL_PIP_INSTALL, "ENV PYTHONPATH=/opt")
        if source_file and os.path.isfile(source_file):
            filename = os.path.basename(source_file)
            img = img._append(f"COPY {filename} /opt/{filename}")
            img._context_files[filename] = source_file
        img = img._append('CMD ["python", "-m", "openmodal.runtime.agent"]')
        return img.build_and_push("default-agent", provider=self)

    def _get_source_mounts(self) -> list[str]:
        """Mount local openmodal source into the container for development."""
        # Mount src/ so that `import openmodal` resolves to local source
        src_dir = Path(__file__).parent.parent.parent.parent  # .../src/
        return ["-v", f"{src_dir}:/opt/openmodal_src", "-e", "PYTHONPATH=/opt/openmodal_src:/opt"]

    def create_instance(
        self, spec: FunctionSpec, image_uri: str | None = None, name: str | None = None,
    ) -> tuple[str, str]:
        name = name or spec.name
        name = name.lower().replace("_", "-")[:63]
        if image_uri is None:
            image_uri = self._ensure_default_agent_image(spec.source_file)

        self._rm(name)

        cmd = [
            "docker", "run", "-d",
            "--name", name,
            "--label", LABEL,
            "--network", "host",
            "--shm-size=16g",
        ]

        cmd += self._get_source_mounts()

        if spec.gpu:
            _check_gpu(spec.gpu)
            cmd += ["--gpus", "all"]

        for mount_path, vol in (spec.volumes or {}).items():
            local_dir = VOLUMES_DIR / vol.name
            local_dir.mkdir(parents=True, exist_ok=True)
            cmd += ["-v", f"{local_dir}:{mount_path}"]

        for secret in (spec.secrets or []):
            if hasattr(secret, "env_dict"):
                for k, v in secret.env_dict.items():
                    cmd += ["-e", f"{k}={v}"]

        cmd.append(image_uri)
        subprocess.run(cmd, check=True, capture_output=True)
        return name, "localhost"

    def delete_instance(self, instance_name: str) -> None:
        self._rm(instance_name)

    def _rm(self, name: str):
        subprocess.run(["docker", "rm", "-f", name], capture_output=True)

    def list_instances(self, app_name: str | None = None) -> list[dict]:
        result = subprocess.run(
            ["docker", "ps", "--filter", f"label={LABEL}", "--format", "{{json .}}"],
            capture_output=True, text=True,
        )
        instances = []
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            data = json.loads(line)
            name = data.get("Names", "")
            if app_name and app_name.lower() not in name.lower():
                continue
            instances.append({
                "name": name,
                "status": data.get("State", data.get("Status", "")),
                "ip": "localhost",
            })
        return instances

    def wait_for_healthy(self, ip: str, port: int, timeout: int = 600) -> bool:
        url = f"http://localhost:{port}/health"
        start = time.time()
        while time.time() - start < timeout:
            try:
                resp = urllib.request.urlopen(url, timeout=5)
                if resp.status == 200:
                    return True
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(2)
        return False

    def machine_spec_str(self, gpu_str: str) -> str:
        if gpu_str:
            return f"local GPU ({gpu_str})"
        return "local CPU"

    def instance_name(self, app_name: str, func_name: str, suffix: str = "") -> str:
        return app_name.lower().replace("_", "-")

    def build_image(self, dockerfile_dir: str, name: str, tag: str) -> str:
        image_uri = f"openmodal-{name}:{tag}"

        result = subprocess.run(
            ["docker", "image", "inspect", image_uri],
            capture_output=True,
        )
        if result.returncode == 0:
            logger.debug(f"Image exists locally: {image_uri}")
            return image_uri

        subprocess.run(
            ["docker", "build", "-t", image_uri, dockerfile_dir],
            check=True, capture_output=True,
        )
        logger.debug(f"Built: {image_uri}")
        return image_uri

    def image_exists(self, image_uri: str) -> bool:
        result = subprocess.run(
            ["docker", "image", "inspect", image_uri],
            capture_output=True,
        )
        return result.returncode == 0

    def create_sandbox_pod(self, name: str, image_uri: str | None, timeout: int = 3600,
                           gpu: str | None = None, cpu: float | None = None,
                           memory: int | None = None, env_vars: dict[str, str] | None = None):
        self._rm(name)

        image = image_uri or "ubuntu:24.04"
        cmd = [
            "docker", "run", "-d",
            "--name", name,
            "--label", LABEL,
        ]

        if gpu:
            _check_gpu(gpu)
            cmd += ["--gpus", "all"]

        for k, v in (env_vars or {}).items():
            cmd += ["-e", f"{k}={v}"]

        cmd += [image, "sleep", str(timeout)]
        subprocess.run(cmd, check=True, capture_output=True)

        for _ in range(30):
            result = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", name],
                capture_output=True, text=True,
            )
            if "true" in result.stdout:
                return
            time.sleep(1)

    def exec_in_pod(self, pod_name: str, *args: str, workdir: str | None = None, env: dict[str, str] | None = None):
        from openmodal.process import ContainerProcess

        command = list(args)
        if len(command) == 1:
            docker_cmd = ["docker", "exec", pod_name, "bash", "-lc", command[0]]
        else:
            docker_cmd = ["docker", "exec"]
            if workdir:
                docker_cmd += ["-w", workdir]
            if env:
                for k, v in env.items():
                    docker_cmd += ["-e", f"{k}={v}"]
            docker_cmd += [pod_name, *command]

        result = subprocess.run(docker_cmd, capture_output=True, text=True)
        return ContainerProcess(
            result.stdout.rstrip("\n"),
            result.stderr.rstrip("\n"),
            result.returncode,
        )

    def copy_to_pod(self, pod_name: str, local_path: str, remote_path: str):
        self.exec_in_pod(pod_name, "bash", "-c", f"mkdir -p $(dirname {remote_path})")
        subprocess.run(
            ["docker", "cp", local_path, f"{pod_name}:{remote_path}"],
            check=True, capture_output=True,
        )

    def copy_from_pod(self, pod_name: str, remote_path: str, local_path: str):
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["docker", "cp", f"{pod_name}:{remote_path}", local_path],
            check=True, capture_output=True,
        )

    def stream_logs(self, instance_name: str, *, follow: bool = True,
                    tail: int | None = None, since: str | None = None,
                    include_stderr: bool = False):
        cmd = ["docker", "logs", instance_name]
        if follow:
            cmd.append("-f")
        if tail is not None:
            cmd += ["--tail", str(tail)]
        if since:
            cmd += ["--since", since]
        try:
            return subprocess.Popen(
                cmd, stdout=sys.stdout,
                stderr=subprocess.STDOUT if include_stderr else subprocess.DEVNULL,
            )
        except Exception:
            return None

    def ensure_volume(self, name: str) -> str:
        vol_dir = VOLUMES_DIR / name
        vol_dir.mkdir(parents=True, exist_ok=True)
        return str(vol_dir)


def get_provider() -> LocalProvider:
    return LocalProvider()
