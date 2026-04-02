"""GCE VM lifecycle — create, delete, list, health check."""

from __future__ import annotations

import base64
import json
import logging
import os
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

from openmodal.function import FunctionSpec
from openmodal.providers.base import CloudProvider
from openmodal.providers.gcp.config import DEFAULT_ZONE, FIREWALL_TAG, get_project, parse_gpu_config
from openmodal.providers.gcp.network import ensure_firewall
from openmodal.providers.gcp.secrets import secrets_script
from openmodal.runtime.agent import DEFAULT_PORT

logger = logging.getLogger("openmodal.compute")

AGENT_PORT = DEFAULT_PORT


def _vm_name(app_name: str, func_name: str = "", suffix: str = "") -> str:
    return app_name.lower().replace("_", "-")[:63]


def _secrets_script(spec: FunctionSpec) -> str:
    if not spec.secrets:
        return ""
    return secrets_script(spec.secrets)


def _startup_script_bare(spec: FunctionSpec) -> str:
    from openmodal.image import OPENMODAL_SRC_DIR

    agent_path = OPENMODAL_SRC_DIR / "runtime" / "agent.py"
    agent_encoded = base64.b64encode(agent_path.read_bytes()).decode()

    source_block = ""
    if spec.source_file:
        source_content = open(spec.source_file).read()
        source_encoded = base64.b64encode(source_content.encode()).decode()
        source_filename = os.path.basename(spec.source_file)
        source_block = f'echo "{source_encoded}" | base64 -d > /opt/{source_filename}'

    py_version = f"{sys.version_info.major}.{sys.version_info.minor}"
    secrets_block = _secrets_script(spec)

    return f"""\
#!/bin/bash
set -ex
apt-get update && apt-get install -y curl
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="/root/.local/bin:$PATH"
uv python install {py_version}
UV_PYTHON=$(uv python find {py_version})
$UV_PYTHON -m pip install --break-system-packages -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ openmodal
{source_block}
export PYTHONPATH=/opt
{secrets_block}echo "{agent_encoded}" | base64 -d > /opt/openmodal_agent.py
$UV_PYTHON /opt/openmodal_agent.py &
"""


def _startup_script_docker(image_uri: str, spec: FunctionSpec, has_gpu: bool = False) -> str:
    registry_host = image_uri.split("/")[0]

    env_flags = '\nDOCKER_ENV_FLAGS=""\n'
    if spec.secrets:
        secrets_block = _secrets_script(spec)
        env_flags += secrets_block
        env_flags += (
            'for key in $(env | grep -v "^_" | cut -d= -f1); do\n'
            '  DOCKER_ENV_FLAGS="$DOCKER_ENV_FLAGS -e $key"\n'
            'done\n'
        )

    gpu_flag = "--gpus all " if has_gpu else ""
    nvidia_setup = ""
    if has_gpu:
        nvidia_setup = """
if ! dpkg -l | grep -q nvidia-container-toolkit; then
    distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \\
        | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -s -L "https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list" \\
        | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \\
        | tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
    apt-get update && apt-get install -y nvidia-container-toolkit
    nvidia-ctk runtime configure --runtime=docker
    systemctl restart docker
fi
"""

    return f"""\
#!/bin/bash
set -ex

if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
fi
{nvidia_setup}
gcloud auth configure-docker {registry_host} --quiet
docker pull {image_uri}
{env_flags}
docker run -d --name openmodal-agent \\
    {gpu_flag}--network host --shm-size=16g \\
    $DOCKER_ENV_FLAGS \\
    {image_uri}
"""


def _startup_script_web_server(
    image_uri: str,
    volume_commands: list[str],
    docker_volume_mounts: list[str],
    scaledown_window: int,
    port: int,
) -> str:
    from openmodal.runtime.startup import render_startup_script
    return render_startup_script(
        image_uri=image_uri,
        volume_commands=volume_commands,
        docker_volume_mounts=docker_volume_mounts,
        scaledown_window=scaledown_window,
        port=port,
    )


def _gce_create(
    name: str,
    machine_type: str,
    startup_script: str,
    project: str,
    gpu_flags: list[str] | None = None,
    boot_disk_size: str = "200GB",
    boot_disk_type: str = "pd-standard",
    metadata_method: str = "file",
) -> str:
    """Low-level GCE instance creation. Returns external IP."""
    if gpu_flags is None:
        gpu_flags = []

    # Delete existing instance with same name if it exists
    try:
        _gce_delete(name, project)
    except Exception:
        pass

    ensure_firewall(project, AGENT_PORT)

    if metadata_method == "file":
        with tempfile.NamedTemporaryFile(mode="w", suffix=".sh", delete=False) as f:
            f.write(startup_script)
            script_path = f.name
        metadata_flag = f"--metadata-from-file=startup-script={script_path}"
    else:
        metadata_flag = f"--metadata=startup-script={startup_script}"
        script_path = None

    cmd = [
        "gcloud", "compute", "instances", "create", name,
        f"--zone={DEFAULT_ZONE}",
        f"--machine-type={machine_type}",
        *gpu_flags,
        f"--boot-disk-size={boot_disk_size}",
        f"--boot-disk-type={boot_disk_type}",
        "--image-family=ubuntu-2204-lts",
        "--image-project=ubuntu-os-cloud",
        f"--tags={FIREWALL_TAG}",
        "--labels=managed-by=openmodal",
        "--scopes=cloud-platform",
        metadata_flag,
        "--project", project,
    ]

    subprocess.run(cmd, check=True, capture_output=True)

    if script_path:
        os.unlink(script_path)

    result = subprocess.run(
        ["gcloud", "compute", "instances", "describe", name,
         f"--zone={DEFAULT_ZONE}", "--project", project,
         "--format=json(networkInterfaces[0].accessConfigs[0].natIP)"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)["networkInterfaces"][0]["accessConfigs"][0]["natIP"]


def _gce_delete(name: str, project: str, zone: str | None = None) -> None:
    zone = zone or DEFAULT_ZONE
    subprocess.run(
        ["gcloud", "compute", "instances", "delete", name,
         f"--zone={zone}", "--project", project, "--quiet"],
        check=True, capture_output=True,
    )


def _gce_list(project: str, filter_str: str) -> list[dict]:
    result = subprocess.run(
        ["gcloud", "compute", "instances", "list",
         f"--filter={filter_str}",
         "--format=json(name,status,networkInterfaces[0].accessConfigs[0].natIP,zone)",
         "--project", project],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout)


class GCPProvider(CloudProvider):
    def create_instance(self, spec: FunctionSpec, image_uri: str | None = None, name: str | None = None) -> tuple[str, str]:
        project = get_project()
        if name is None:
            name = _vm_name(spec._app_name, spec.name) if hasattr(spec, "_app_name") else _vm_name("app", spec.name)

        has_image = spec.image is not None and image_uri is not None

        if has_image:
            if spec.web_server_port:
                return self._create_web_server_instance(spec, image_uri, project, name)
            return self._create_docker_agent_instance(spec, image_uri, project, name)
        return self._create_bare_agent_instance(spec, project, name)

    def _create_web_server_instance(
        self, spec: FunctionSpec, image_uri: str, project: str, name: str
    ) -> tuple[str, str]:
        machine_type, accel_type, accel_count = parse_gpu_config(spec.gpu)
        port = spec.web_server_port or 8000

        volume_cmds = []
        docker_mounts = []
        for mount_path, vol in spec.volumes.items():
            vol._ensure_bucket()
            volume_cmds.append(vol.mount_command(f"/mnt/volumes{mount_path}"))
            docker_mounts.append(f"-v /mnt/volumes{mount_path}:{mount_path}")

        startup_script = _startup_script_web_server(
            image_uri=image_uri,
            volume_commands=volume_cmds,
            docker_volume_mounts=docker_mounts,
            scaledown_window=spec.scaledown_window,
            port=port,
        )

        ensure_firewall(project, port)

        gpu_flags = [
            f"--accelerator=type={accel_type},count={accel_count}",
            "--maintenance-policy=TERMINATE",
        ]

        ip = _gce_create(
            name=name,
            machine_type=machine_type,
            startup_script=startup_script,
            project=project,
            gpu_flags=gpu_flags,
            boot_disk_size="200GB",
            boot_disk_type="pd-ssd",
            metadata_method="inline",
        )
        return name, ip

    def _create_docker_agent_instance(
        self, spec: FunctionSpec, image_uri: str, project: str, name: str
    ) -> tuple[str, str]:
        startup_script = _startup_script_docker(image_uri, spec, has_gpu=bool(spec.gpu))

        if spec.gpu:
            machine_type, accel_type, accel_count = parse_gpu_config(spec.gpu)
            gpu_flags = [
                f"--accelerator=type={accel_type},count={accel_count}",
                "--maintenance-policy=TERMINATE",
            ]
        else:
            machine_type = "e2-small"
            gpu_flags = []

        ip = _gce_create(
            name=name,
            machine_type=machine_type,
            startup_script=startup_script,
            project=project,
            gpu_flags=gpu_flags,
            boot_disk_size="200GB",
        )
        return name, ip

    def _create_bare_agent_instance(
        self, spec: FunctionSpec, project: str, name: str
    ) -> tuple[str, str]:
        startup_script = _startup_script_bare(spec)

        if spec.gpu:
            machine_type, accel_type, accel_count = parse_gpu_config(spec.gpu)
            gpu_flags = [
                f"--accelerator=type={accel_type},count={accel_count}",
                "--maintenance-policy=TERMINATE",
            ]
        else:
            machine_type = "e2-small"
            gpu_flags = []

        ip = _gce_create(
            name=name,
            machine_type=machine_type,
            startup_script=startup_script,
            project=project,
            gpu_flags=gpu_flags,
            boot_disk_size="50GB",
        )
        return name, ip

    def delete_instance(self, instance_name: str) -> None:
        project = get_project()
        try:
            _gce_delete(instance_name, project)
            logger.debug(f"Deleted instance: {instance_name}")
        except Exception:
            logger.warning(f"Failed to delete instance: {instance_name}")

    def list_instances(self, app_name: str | None = None) -> list[dict]:
        project = get_project()
        if app_name:
            filter_str = f"name={app_name.lower().replace('_', '-')}"
        else:
            filter_str = "labels.managed-by=openmodal"
        raw = _gce_list(project, filter_str)
        return [
            {
                "name": vm.get("name", ""),
                "status": vm.get("status", ""),
                "ip": (vm.get("networkInterfaces", [{}])[0]
                       .get("accessConfigs", [{}])[0]
                       .get("natIP", "")),
            }
            for vm in raw
        ]

    def wait_for_healthy(self, ip: str, port: int, timeout: int = 600) -> bool:
        url = f"http://{ip}:{port}/health"
        start = time.time()
        logger.debug(f"Waiting for {url} (timeout: {timeout}s)...")

        while time.time() - start < timeout:
            try:
                req = urllib.request.urlopen(url, timeout=5)
                if req.status == 200:
                    logger.debug(f"Healthy after {time.time() - start:.0f}s")
                    return True
            except (urllib.error.URLError, OSError):
                pass
            time.sleep(5)

        logger.error(f"Not healthy after {timeout}s")
        return False

    def instance_name(self, app_name: str, func_name: str, suffix: str = "") -> str:
        return _vm_name(app_name, func_name, suffix)

    def machine_spec_str(self, gpu_str: str) -> str:
        from openmodal.providers.gcp.config import machine_spec_str
        if gpu_str:
            machine_type, _, accel_count = parse_gpu_config(gpu_str)
            gpu_name = gpu_str.split(":")[0]
            return machine_spec_str(machine_type, gpu_name, accel_count)
        return machine_spec_str("e2-small")


def get_provider() -> GCPProvider:
    return GCPProvider()


# Backwards-compatible module-level functions used by CLI commands.
# These delegate to the provider so callers don't need to instantiate it.

_provider = GCPProvider()


def create_vm(spec: FunctionSpec, image_uri: str, app_name: str = "app") -> str:
    spec._app_name = app_name
    _, ip = _provider.create_instance(spec, image_uri)
    return ip


def delete_vm(app_name: str, func_name: str) -> None:
    name = _vm_name(app_name, func_name)
    project = get_project()
    _gce_delete(name, project)


def list_vms(app_name: str | None = None) -> list[dict]:
    return _provider.list_instances(app_name)


def wait_for_healthy(ip: str, port: int, timeout: int = 600, path: str = "/health") -> bool:
    return _provider.wait_for_healthy(ip, port, timeout)
