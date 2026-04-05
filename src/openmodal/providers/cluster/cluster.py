"""Cluster provider — runs on bare-metal SSH clusters (no Docker, no SLURM)."""

from __future__ import annotations

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
from openmodal.providers.cluster import ssh
from openmodal.providers.cluster.config import (
    get_default_node,
    get_env_setup_script,
    get_remote_base,
)

logger = logging.getLogger("openmodal.cluster")


def _wrap_cmd(command: str) -> str:
    """Wrap a command with the env setup script if configured."""
    script = get_env_setup_script()
    if script:
        return f"source {script} && {command}"
    return command


class ClusterProvider(CloudProvider):

    def __init__(self, node: str | None = None):
        self.node = node or get_default_node()
        self._base = get_remote_base()
        self._envs = f"{self._base}/envs"
        self._logs = f"{self._base}/logs"
        self._pids = f"{self._base}/pids"
        self._code = f"{self._base}/code"
        self._volumes = f"{self._base}/volumes"

    def preflight_check(self, spec: FunctionSpec) -> None:
        if not ssh.is_reachable(self.node):
            raise RuntimeError(
                f"Cannot SSH to {self.node}. Open a connection first:\n"
                f"  ssh {self.node} 'hostname'\n"
                f"(enter your password to open the ControlMaster socket)"
            )
        ssh.run(self.node, f"mkdir -p {self._envs} {self._logs} {self._pids} {self._code} {self._volumes}")

    def _ensure_default_env(self, source_file: str | None = None) -> str:
        """Create a minimal venv with just openmodal + copy source file."""
        venv_path = f"{self._envs}/default"
        result = ssh.run(self.node, f"test -d {venv_path}/bin && echo exists", check=False)
        if "exists" not in result.stdout:
            ssh.run(self.node, _wrap_cmd(f"uv venv {venv_path} --python 3.12"), timeout=120)
            ssh.run(
                self.node,
                _wrap_cmd(f"uv pip install --python {venv_path}/bin/python openmodal"),
                timeout=300,
            )

        code_dir = f"{self._code}/default"
        ssh.run(self.node, f"mkdir -p {code_dir}")
        if source_file and os.path.isfile(source_file):
            ssh.scp_to(source_file, self.node, f"{code_dir}/{os.path.basename(source_file)}")

        return venv_path

    def build_image(self, dockerfile_dir: str, name: str, tag: str) -> str:
        """Instead of building a Docker image, create a uv venv on the remote host.

        Parses pip install commands from the Dockerfile and installs them
        into a venv. Returns a venv path as the "image URI".
        """
        dockerfile = Path(dockerfile_dir) / "Dockerfile"
        pip_packages = []

        if dockerfile.exists():
            for line in dockerfile.read_text().splitlines():
                line = line.strip()
                if line.startswith("RUN pip install"):
                    parts = line.removeprefix("RUN pip install").strip()
                    pip_packages.extend(_extract_packages(parts))
                elif "uv pip install" in line:
                    parts = line.split("uv pip install", 1)[1].strip()
                    pip_packages.extend(_extract_packages(parts))

        if not any("openmodal" in p for p in pip_packages):
            pip_packages.insert(0, "openmodal")

        venv_path = f"{self._envs}/{tag}"

        result = ssh.run(self.node, f"test -d {venv_path}/bin && echo exists", check=False)
        if "exists" in result.stdout:
            logger.debug(f"Reusing cached venv: {venv_path}")
        else:
            logger.debug(f"Creating venv: {venv_path}")
            ssh.run(self.node, _wrap_cmd(f"uv venv {venv_path} --python 3.12"), timeout=120)
            if pip_packages:
                pkg_str = " ".join(f'"{p}"' for p in pip_packages)
                ssh.run(
                    self.node,
                    _wrap_cmd(f"uv pip install --python {venv_path}/bin/python {pkg_str}"),
                    timeout=600,
                )

        # Copy source files from the build context to remote
        code_dir = f"{self._code}/{tag}"
        ssh.run(self.node, f"mkdir -p {code_dir}")
        for fname in os.listdir(dockerfile_dir):
            if fname == "Dockerfile":
                continue
            local_file = os.path.join(dockerfile_dir, fname)
            if os.path.isfile(local_file):
                ssh.scp_to(local_file, self.node, f"{code_dir}/{fname}")

        return venv_path

    def image_exists(self, image_uri: str) -> bool:
        result = ssh.run(self.node, f"test -d {image_uri}/bin && echo exists", check=False)
        return "exists" in result.stdout

    def create_instance(
        self, spec: FunctionSpec, image_uri: str | None = None, name: str | None = None,
    ) -> tuple[str, str]:
        name = name or spec.name
        name = name.lower().replace("_", "-")[:63]

        self._kill(name)

        if image_uri is None:
            image_uri = self._ensure_default_env(spec.source_file)

        venv_path = image_uri
        tag = os.path.basename(venv_path)
        code_dir = f"{self._code}/{tag}"

        # Build env vars string
        env_parts = [f"PYTHONPATH={code_dir}"]
        for secret in (spec.secrets or []):
            if hasattr(secret, "env_dict"):
                for k, v in secret.env_dict.items():
                    env_parts.append(f"{k}={v}")
        env_vars = " ".join(env_parts)

        python = f"{venv_path}/bin/python"
        launch_cmd = f"{env_vars} {python} -m openmodal.runtime.agent"

        log_file = f"{self._logs}/{name}.log"
        pid_file = f"{self._pids}/{name}.pid"

        pid = ssh.run_background(
            self.node,
            _wrap_cmd(launch_cmd),
            log_file=log_file,
        )

        ssh.run(self.node, f"echo {pid} > {pid_file}")

        # Get the FQDN for direct access
        result = ssh.run(self.node, "hostname -f")
        hostname = result.stdout.strip()

        return name, hostname

    def delete_instance(self, instance_name: str) -> None:
        self._kill(instance_name)

    def _kill(self, name: str) -> None:
        pid_file = f"{self._pids}/{name}.pid"
        ssh.run(
            self.node,
            f"if [ -f {pid_file} ]; then kill $(cat {pid_file}) 2>/dev/null; rm -f {pid_file}; fi",
            check=False,
        )

    def list_instances(self, app_name: str | None = None) -> list[dict]:
        result = ssh.run(self.node, f"ls {self._pids}/*.pid 2>/dev/null", check=False)
        instances = []
        for line in result.stdout.strip().splitlines():
            if not line:
                continue
            name = os.path.basename(line).removesuffix(".pid")
            if app_name and app_name.lower() not in name.lower():
                continue
            pid_result = ssh.run(
                self.node,
                f"kill -0 $(cat {line}) 2>/dev/null && echo running || echo stopped",
                check=False,
            )
            status = "running" if "running" in pid_result.stdout else "stopped"
            instances.append({"name": name, "status": status, "ip": self.node})
        return instances

    def wait_for_healthy(self, ip: str, port: int, timeout: int = 600) -> bool:
        url = f"http://{ip}:{port}/health"
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
            return f"{self.node} ({gpu_str})"
        return f"{self.node} (CPU)"

    def instance_name(self, app_name: str, func_name: str, suffix: str = "") -> str:
        return app_name.lower().replace("_", "-")

    def exec_in_pod(
        self,
        pod_name: str,
        *args: str,
        workdir: str | None = None,
        env: dict[str, str] | None = None,
        container: str = "main",
    ):
        from openmodal.process import ContainerProcess

        command = " ".join(args) if len(args) > 1 else args[0]
        if workdir:
            command = f"cd {workdir} && {command}"
        if env:
            env_str = " ".join(f"{k}={v}" for k, v in env.items())
            command = f"{env_str} {command}"

        result = ssh.run(self.node, _wrap_cmd(command), check=False)
        return ContainerProcess(
            result.stdout.rstrip("\n"),
            result.stderr.rstrip("\n"),
            result.returncode,
        )

    def copy_to_pod(self, pod_name: str, local_path: str, remote_path: str):
        ssh.run(self.node, f"mkdir -p $(dirname {remote_path})")
        ssh.scp_to(local_path, self.node, remote_path)

    def copy_from_pod(self, pod_name: str, remote_path: str, local_path: str):
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        ssh.scp_from(self.node, remote_path, local_path)

    def stream_logs(self, instance_name: str, *, follow: bool = True,
                    tail: int | None = None, since: str | None = None,
                    include_stderr: bool = False):
        log_file = f"{self._logs}/{instance_name}.log"
        cmd = ["ssh", self.node]
        tail_cmd = "tail"
        if follow:
            tail_cmd += " -f"
        if tail is not None:
            tail_cmd += f" -n {tail}"
        tail_cmd += f" {log_file}"
        cmd.append(tail_cmd)
        try:
            return subprocess.Popen(
                cmd, stdout=sys.stdout,
                stderr=subprocess.STDOUT if include_stderr else subprocess.DEVNULL,
            )
        except Exception:
            return None

    def ensure_volume(self, name: str) -> str:
        vol_dir = f"{self._volumes}/{name}"
        ssh.run(self.node, f"mkdir -p {vol_dir}")
        return vol_dir


def _extract_packages(text: str) -> list[str]:
    """Extract package names from a pip install argument string."""
    packages = []
    in_quote = False
    current = ""
    for char in text:
        if char == '"':
            if in_quote:
                if current.strip():
                    packages.append(current.strip())
                current = ""
            in_quote = not in_quote
        elif in_quote:
            current += char

    if not packages:
        for token in text.split():
            if token.startswith("-"):
                continue
            packages.append(token)

    return packages
