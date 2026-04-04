"""Azure AKS provider — Kubernetes-based compute on Azure."""

from __future__ import annotations

import contextlib
import logging
import os
import time
import urllib.error
import urllib.request

from kubernetes import client, config, watch

from openmodal.function import FunctionSpec
from openmodal.providers.azure.config import (
    DEFAULT_LOCATION,
    GPU_MAP,
    RESOURCE_GROUP,
    get_acr_name,
    get_subscription_id,
    machine_spec_str,
    parse_gpu_config,
)
from openmodal.providers.base import CloudProvider

logger = logging.getLogger("openmodal.azure.aks")

NAMESPACE = "default"
LABEL_MANAGED_BY = "openmodal"
SYNC_IMAGE = "mcr.microsoft.com/azure-cli:latest"


def _k8s_name(name: str) -> str:
    return name.lower().replace("_", "-")[:63]


def _gpu_node_selector(gpu_str: str) -> tuple[str, int]:
    """Returns (vm_size, gpu count)."""
    parts = gpu_str.replace("!", "").split(":")
    gpu_name = parts[0].upper()
    count = int(parts[1]) if len(parts) > 1 else 1

    if gpu_name not in GPU_MAP:
        raise ValueError(f"Unknown GPU: {gpu_name}. Available: {list(GPU_MAP.keys())}")

    vm_size, _ = GPU_MAP[gpu_name]
    return vm_size, count


def _build_pod_spec(
    spec: FunctionSpec,
    image_uri: str,
    name: str,
    command: list[str] | None = None,
) -> client.V1Pod:
    resources = client.V1ResourceRequirements(requests={}, limits={})
    node_selector = {}
    tolerations = []

    if spec.gpu:
        _vm_size, gpu_count = _gpu_node_selector(spec.gpu)
        resources.limits["nvidia.com/gpu"] = str(gpu_count)
        resources.requests["nvidia.com/gpu"] = str(gpu_count)
        node_selector["agentpool"] = spec.gpu.lower().replace("-", "")
        tolerations.append(client.V1Toleration(
            key="nvidia.com/gpu", operator="Exists", effect="NoSchedule",
        ))

    env_vars = []
    if spec.source_file:
        env_vars.append(client.V1EnvVar(name="PYTHONPATH", value="/opt"))

    for secret in (spec.secrets or []):
        if hasattr(secret, "env_dict"):
            for k, v in secret.env_dict.items():
                env_vars.append(client.V1EnvVar(name=k, value=v))

    container = client.V1Container(
        name="main",
        image=image_uri,
        command=command,
        env=env_vars or None,
        resources=resources,
        ports=[client.V1ContainerPort(container_port=spec.web_server_port or 8000)]
        if spec.web_server_port else None,
        volume_mounts=[
            client.V1VolumeMount(name="dshm", mount_path="/dev/shm"),
        ],
    )

    if spec.web_server_port:
        container.readiness_probe = client.V1Probe(
            http_get=client.V1HTTPGetAction(path="/health", port=spec.web_server_port),
            initial_delay_seconds=60,
            period_seconds=10,
            failure_threshold=60,
            timeout_seconds=5,
        )
        container.startup_probe = client.V1Probe(
            http_get=client.V1HTTPGetAction(path="/health", port=spec.web_server_port),
            initial_delay_seconds=30,
            period_seconds=10,
            failure_threshold=120,
            timeout_seconds=5,
        )

    volumes = [
        client.V1Volume(
            name="dshm",
            empty_dir=client.V1EmptyDirVolumeSource(medium="Memory", size_limit="16Gi"),
        ),
    ]

    init_containers = []
    sidecar_containers = []
    if spec.volumes:
        from openmodal.providers.volume_helpers import build_volume_specs
        vol_volumes, vol_mounts, init_containers, sidecar_containers = build_volume_specs(spec, SYNC_IMAGE)
        volumes.extend(vol_volumes)
        container.volume_mounts.extend(vol_mounts)

    return client.V1Pod(
        metadata=client.V1ObjectMeta(
            name=name,
            labels={"app": name, "managed-by": LABEL_MANAGED_BY},
        ),
        spec=client.V1PodSpec(
            node_selector=node_selector or None,
            tolerations=tolerations or None,
            init_containers=init_containers or None,
            containers=[container, *sidecar_containers],
            restart_policy="Never",
            termination_grace_period_seconds=120 if spec.volumes else 30,
            volumes=volumes,
        ),
    )


class AKSProvider(CloudProvider):
    def preflight_check(self, spec):
        import shutil
        import subprocess
        if not shutil.which("az"):
            raise RuntimeError("az CLI not found. Run 'openmodal setup azure' to get started.")
        result = subprocess.run(
            ["az", "account", "show"],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            raise RuntimeError("Not logged in to Azure. Run: az login")

    def __init__(self):
        from openmodal.providers.azure.aks_setup import cluster_exists, update_kubeconfig
        # Always check if AKS cluster exists and switch context to it
        if cluster_exists():
            update_kubeconfig()
            config.load_kube_config()
        else:
            self._auto_provision_cluster()
            config.load_kube_config()
        self._v1 = client.CoreV1Api()
        self._apps_v1 = client.AppsV1Api()

    def _auto_provision_cluster(self):
        from openmodal.cli.console import Spinner, success
        from openmodal.providers.azure.aks_setup import cluster_exists, setup_cluster, update_kubeconfig

        if cluster_exists():
            update_kubeconfig()
            return

        import logging as _logging
        _logging.disable(_logging.INFO)
        with Spinner("Creating AKS cluster (one-time, ~5 min)...") as spinner:
            setup_cluster()
        _logging.disable(_logging.NOTSET)
        success(f"AKS cluster ready. ({int(spinner.elapsed)}s)")

    def _delete_if_exists(self, delete_fn, read_fn, timeout: int = 30):
        try:
            delete_fn()
        except client.exceptions.ApiException:
            return
        start = time.time()
        while time.time() - start < timeout:
            try:
                read_fn()
                time.sleep(2)
            except client.exceptions.ApiException:
                return

    # ── Default agent image ───────────────────────────────────────────

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

    # ── Core instance management ──────────────────────────────────────

    def create_instance(
        self, spec: FunctionSpec, image_uri: str | None = None, name: str | None = None,
    ) -> tuple[str, str]:
        name = name or _k8s_name(getattr(spec, "_app_name", "app"))
        if image_uri is None:
            image_uri = self._ensure_default_agent_image(spec.source_file)

        if spec.web_server_port:
            return self._create_deployment(spec, image_uri, name)
        return self._create_pod(spec, image_uri, name)

    def _create_deployment(self, spec: FunctionSpec, image_uri: str, name: str) -> tuple[str, str]:
        pod_template = _build_pod_spec(spec, image_uri, name)

        deployment = client.V1Deployment(
            metadata=client.V1ObjectMeta(
                name=name,
                labels={"app": name, "managed-by": LABEL_MANAGED_BY},
            ),
            spec=client.V1DeploymentSpec(
                replicas=1,
                selector=client.V1LabelSelector(match_labels={"app": name}),
                template=client.V1PodTemplateSpec(
                    metadata=pod_template.metadata,
                    spec=pod_template.spec,
                ),
            ),
        )
        deployment.spec.template.spec.restart_policy = "Always"

        self._delete_if_exists(
            lambda: self._apps_v1.delete_namespaced_deployment(name, NAMESPACE),
            lambda: self._apps_v1.read_namespaced_deployment(name, NAMESPACE),
        )
        self._apps_v1.create_namespaced_deployment(NAMESPACE, deployment)

        service = client.V1Service(
            metadata=client.V1ObjectMeta(
                name=name,
                labels={"app": name, "managed-by": LABEL_MANAGED_BY},
            ),
            spec=client.V1ServiceSpec(
                type="LoadBalancer",
                selector={"app": name},
                ports=[client.V1ServicePort(
                    port=spec.web_server_port,
                    target_port=spec.web_server_port,
                    protocol="TCP",
                )],
            ),
        )

        self._delete_if_exists(
            lambda: self._v1.delete_namespaced_service(name, NAMESPACE),
            lambda: self._v1.read_namespaced_service(name, NAMESPACE),
        )
        self._v1.create_namespaced_service(NAMESPACE, service)

        if spec.scaledown_window > 0 and spec.web_server_port:
            self._create_keda_scaledown(name, spec.scaledown_window, spec.web_server_port)

        ip = self._wait_for_external_ip(name, timeout=300)
        return name, ip

    def _create_keda_scaledown(self, name: str, scaledown_window: int, port: int):
        """Create a KEDA ScaledObject for scale-to-zero."""
        from kubernetes.client import CustomObjectsApi
        custom = CustomObjectsApi()

        scaled_object = {
            "apiVersion": "keda.sh/v1alpha1",
            "kind": "ScaledObject",
            "metadata": {
                "name": f"{name}-scaledown",
                "namespace": NAMESPACE,
                "labels": {"managed-by": LABEL_MANAGED_BY},
            },
            "spec": {
                "scaleTargetRef": {"name": name},
                "minReplicaCount": 0,
                "maxReplicaCount": 1,
                "cooldownPeriod": scaledown_window,
                "idleReplicaCount": 0,
                "triggers": [{
                    "type": "kubernetes-workload",
                    "metadata": {
                        "podSelector": f"app={name}",
                        "value": "1",
                    },
                }],
            },
        }

        with contextlib.suppress(client.exceptions.ApiException):
            custom.delete_namespaced_custom_object(
                "keda.sh", "v1alpha1", NAMESPACE, "scaledobjects", f"{name}-scaledown",
            )

        custom.create_namespaced_custom_object(
            "keda.sh", "v1alpha1", NAMESPACE, "scaledobjects", scaled_object,
        )

    def _create_pod(self, spec: FunctionSpec, image_uri: str, name: str) -> tuple[str, str]:
        pod = _build_pod_spec(spec, image_uri, name)
        self._v1.create_namespaced_pod(NAMESPACE, pod)
        timeout = 1200 if spec.gpu else 600
        self._wait_for_pod_running(name, timeout=timeout)

        # AKS pod IPs are not directly routable from the client,
        # so we use kubectl port-forward to proxy the connection.
        port = spec.web_server_port or 50051
        self._start_port_forward(name, port)
        return name, "localhost"

    def _start_port_forward(self, pod_name: str, port: int):
        """Start kubectl port-forward in the background."""
        import subprocess
        self._port_forward_proc = subprocess.Popen(
            ["kubectl", "port-forward", f"pod/{pod_name}", f"{port}:{port}", "-n", NAMESPACE],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        time.sleep(2)

    def _wait_for_external_ip(self, name: str, timeout: int = 300) -> str:
        start = time.time()
        while time.time() - start < timeout:
            svc = self._v1.read_namespaced_service(name, NAMESPACE)
            ingress = svc.status.load_balancer.ingress
            if ingress:
                return ingress[0].ip or ingress[0].hostname
            time.sleep(5)
        raise TimeoutError(f"Service {name} did not get an external IP within {timeout}s")

    def _wait_for_pod_running(self, name: str, timeout: int = 600):
        w = watch.Watch()
        for event in w.stream(
            self._v1.list_namespaced_pod,
            NAMESPACE,
            field_selector=f"metadata.name={name}",
            timeout_seconds=timeout,
        ):
            pod = event["object"]
            if (
                pod.status.phase == "Running"
                and pod.status.pod_ip
                and pod.status.container_statuses
                and all(
                    cs.ready or (cs.state and cs.state.running)
                    for cs in pod.status.container_statuses
                )
            ):
                w.stop()
                return
            if pod.status.phase in ("Failed", "Unknown"):
                w.stop()
                reason = self._get_pod_failure_reason(name)
                raise RuntimeError(f"Pod {name} failed: {reason}")

        reason = self._get_pod_failure_reason(name)
        raise RuntimeError(f"Pod {name} not ready after {timeout}s: {reason}")

    def _get_pod_failure_reason(self, name: str) -> str:
        """Check events in priority order: mount errors > image pull > crash > scheduling."""
        try:
            events = self._v1.list_namespaced_event(
                NAMESPACE, field_selector=f"involvedObject.name={name}",
            )
            for e in reversed(events.items):
                if e.reason == "FailedMount":
                    return f"Volume mount failed: {e.message}"
            for e in reversed(events.items):
                if e.reason in ("ErrImagePull", "ImagePullBackOff"):
                    return f"Failed to pull container image: {e.message}"
            for e in reversed(events.items):
                if e.reason == "BackOff":
                    return f"Container keeps crashing: {e.message}"

            pod = self._v1.read_namespaced_pod(name, NAMESPACE)
            if pod.status.phase == "Pending":
                for e in reversed(events.items):
                    if e.reason == "FailedScheduling":
                        return f"Pod couldn't be scheduled: {e.message}"
                return "Pod is still Pending — likely waiting for a GPU node to scale up."
            return f"Pod status: {pod.status.phase}"
        except Exception:
            return "Could not determine reason. Run 'kubectl describe pod' for details."

    def delete_instance(self, instance_name: str) -> None:
        if hasattr(self, "_port_forward_proc") and self._port_forward_proc:
            self._port_forward_proc.terminate()
            self._port_forward_proc = None

        from kubernetes.client import BatchV1Api, CustomObjectsApi
        BatchV1Api()
        custom = CustomObjectsApi()

        for api_call in [
            lambda: self._apps_v1.delete_namespaced_deployment(instance_name, NAMESPACE),
            lambda: self._v1.delete_namespaced_service(instance_name, NAMESPACE),
            lambda: self._v1.delete_namespaced_pod(instance_name, NAMESPACE),
            lambda: custom.delete_namespaced_custom_object(
                "keda.sh", "v1alpha1", NAMESPACE, "scaledobjects", f"{instance_name}-scaledown",
            ),
        ]:
            with contextlib.suppress(client.exceptions.ApiException):
                api_call()

    def list_instances(self, app_name: str | None = None) -> list[dict]:
        label_selector = f"managed-by={LABEL_MANAGED_BY}"
        if app_name:
            label_selector += f",app={_k8s_name(app_name)}"

        pods = self._v1.list_namespaced_pod(NAMESPACE, label_selector=label_selector)
        return [
            {"name": pod.metadata.name, "status": pod.status.phase, "ip": pod.status.pod_ip or ""}
            for pod in pods.items
        ]

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
            time.sleep(5)
        return False

    # ── Machine specs ─────────────────────────────────────────────────

    def machine_spec_str(self, gpu_str: str) -> str:
        if not gpu_str:
            return machine_spec_str("Standard_B2s")
        vm_size, gpu_name, count = parse_gpu_config(gpu_str)
        return machine_spec_str(vm_size, gpu_name, count)

    def instance_name(self, app_name: str, func_name: str, suffix: str = "") -> str:
        return _k8s_name(app_name)

    # ── Sandboxes ─────────────────────────────────────────────────────

    def create_sandbox_pod(
        self, name: str, image_uri: str | None, timeout: int = 3600,
        gpu: str | None = None, cpu: float | None = None, memory: int | None = None,
        env_vars: dict[str, str] | None = None,
    ):
        image = image_uri or "ubuntu:24.04"
        resources = client.V1ResourceRequirements(requests={}, limits={})
        node_selector = {}
        tolerations = []

        if gpu:
            _vm_size, gpu_count = _gpu_node_selector(gpu)
            resources.limits["nvidia.com/gpu"] = str(gpu_count)
            resources.requests["nvidia.com/gpu"] = str(gpu_count)
            tolerations.append(client.V1Toleration(
                key="nvidia.com/gpu", operator="Exists", effect="NoSchedule",
            ))
        resources.requests["cpu"] = str(cpu or 0.25)
        resources.requests["memory"] = f"{memory or 256}Mi"

        env_list = [client.V1EnvVar(name=k, value=v) for k, v in (env_vars or {}).items()]

        pod = client.V1Pod(
            metadata=client.V1ObjectMeta(
                name=name,
                labels={"app": name, "managed-by": LABEL_MANAGED_BY},
            ),
            spec=client.V1PodSpec(
                node_selector=node_selector or None,
                tolerations=tolerations or None,
                containers=[client.V1Container(
                    name="main",
                    image=image,
                    command=["sleep", str(timeout)],
                    env=env_list or None,
                    resources=resources,
                )],
                restart_policy="Never",
            ),
        )
        self._v1.create_namespaced_pod(NAMESPACE, pod)
        self._wait_for_pod_running(name)

    def exec_in_pod(
        self,
        pod_name: str,
        *args: str,
        workdir: str | None = None,
        env: dict[str, str] | None = None,
        container: str = "main",
    ):
        from kubernetes.stream import stream

        from openmodal.process import ContainerProcess

        command = list(args)
        if workdir and command[0] == "bash" and "-c" in command:
            idx = command.index("-c")
            if idx + 1 < len(command):
                command[idx + 1] = f"cd {workdir} && {command[idx + 1]}"
        elif workdir:
            command = ["bash", "-c", f"cd {workdir} && {' '.join(command)}"]

        if env and command[0] == "bash" and "-c" in command:
            idx = command.index("-c")
            if idx + 1 < len(command):
                prefix = " ".join(f"export {k}={v};" for k, v in env.items())
                command[idx + 1] = f"{prefix} {command[idx + 1]}"

        resp = stream(
            self._v1.connect_get_namespaced_pod_exec,
            name=pod_name,
            namespace=NAMESPACE,
            container=container,
            command=command,
            stderr=True, stdout=True, stdin=False, tty=False,
            _preload_content=False,
        )
        stdout = ""
        stderr = ""
        while resp.is_open():
            resp.update(timeout=1)
            if resp.peek_stdout():
                stdout += resp.read_stdout()
            if resp.peek_stderr():
                stderr += resp.read_stderr()
        resp.close()
        returncode = resp.returncode if hasattr(resp, "returncode") else 0
        return ContainerProcess(stdout.rstrip("\n"), stderr.rstrip("\n"), returncode)

    def copy_to_pod(self, pod_name: str, local_path: str, remote_path: str):
        import subprocess
        from pathlib import PurePosixPath
        parent = str(PurePosixPath(remote_path).parent)
        self.exec_in_pod(pod_name, "bash", "-c", f"mkdir -p {parent}")
        subprocess.run(
            ["kubectl", "cp", local_path, f"{NAMESPACE}/{pod_name}:{remote_path}"],
            check=True, capture_output=True,
        )

    def copy_from_pod(self, pod_name: str, remote_path: str, local_path: str):
        import subprocess
        from pathlib import Path
        Path(local_path).parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["kubectl", "cp", f"{NAMESPACE}/{pod_name}:{remote_path}", local_path],
            check=True, capture_output=True,
        )

    # ── Images ────────────────────────────────────────────────────────

    def build_image(self, dockerfile_dir: str, name: str, tag: str) -> str:
        from openmodal.providers.azure.acr import ensure_registry, get_registry_url
        from openmodal.providers.azure.build import acr_build

        subscription_id = get_subscription_id()
        acr_name = get_acr_name(subscription_id)
        image_uri = get_registry_url(acr_name, name, tag)

        if self.image_exists(image_uri):
            return image_uri

        ensure_registry(acr_name, RESOURCE_GROUP, DEFAULT_LOCATION)
        acr_build(dockerfile_dir, image_uri, acr_name)
        return image_uri

    def image_exists(self, image_uri: str) -> bool:
        import subprocess
        # image_uri: acrname.azurecr.io/name:tag
        try:
            parts = image_uri.split("/", 1)
            acr_name = parts[0].split(".")[0]
            repo_tag = parts[1]
            repo, tag = repo_tag.rsplit(":", 1)
            result = subprocess.run(
                ["az", "acr", "repository", "show-tags",
                 "--name", acr_name, "--repository", repo, "-o", "tsv"],
                capture_output=True, text=True,
            )
            return tag in result.stdout.split()
        except Exception:
            return False

    # ── Volumes ───────────────────────────────────────────────────────

    def ensure_volume(self, name: str) -> str:
        from openmodal.providers.azure.storage import ensure_container, ensure_storage_account

        subscription_id = get_subscription_id()
        # Storage account names: alphanumeric, 3-24 chars
        account_name = f"openmodal{subscription_id.replace('-', '')[:8]}"
        ensure_storage_account(account_name, RESOURCE_GROUP, DEFAULT_LOCATION)
        ensure_container(account_name, name)
        return f"azure://{account_name}/{name}"

    # ── Logs ──────────────────────────────────────────────────────────

    def stream_logs(self, instance_name: str, *, follow: bool = True,
                    tail: int | None = None, since: str | None = None,
                    include_stderr: bool = False):
        import subprocess
        import sys
        cmd = ["kubectl", "logs", instance_name, "-n", NAMESPACE, "-c", "main"]
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
