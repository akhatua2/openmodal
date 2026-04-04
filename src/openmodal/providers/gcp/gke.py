"""GKE provider — Kubernetes-based compute using the Python kubernetes client."""

from __future__ import annotations

import contextlib
import logging
import time
import urllib.error
import urllib.request

from kubernetes import client, config, watch

from openmodal.function import FunctionSpec
from openmodal.providers.base import CloudProvider
from openmodal.providers.gcp.config import (
    machine_spec_str,
    parse_gpu_config,
)

logger = logging.getLogger("openmodal.gke")

NAMESPACE = "default"
LABEL_MANAGED_BY = "openmodal"
SYNC_IMAGE = "gcr.io/google.com/cloudsdktool/google-cloud-cli:slim"


def _k8s_name(name: str) -> str:
    return name.lower().replace("_", "-")[:63]


def _gpu_node_selector(gpu_str: str) -> tuple[str, int]:
    """Returns (gpu-type label value, gpu count)."""
    parts = gpu_str.replace("!", "").split(":")
    gpu_name = parts[0].lower()
    count = int(parts[1]) if len(parts) > 1 else 1
    return gpu_name, count


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
        gpu_type, gpu_count = _gpu_node_selector(spec.gpu)
        resources.limits["nvidia.com/gpu"] = str(gpu_count)
        resources.requests["nvidia.com/gpu"] = str(gpu_count)
        node_selector["gpu-type"] = gpu_type
        tolerations.append(client.V1Toleration(
            key="nvidia.com/gpu", operator="Exists", effect="NoSchedule",
        ))

    env_vars = []
    if spec.gpu:
        env_vars.append(client.V1EnvVar(
            name="LD_LIBRARY_PATH",
            value="/usr/local/nvidia/lib64:/usr/local/cuda/lib64",
        ))
        env_vars.append(client.V1EnvVar(name="NVIDIA_VISIBLE_DEVICES", value="all"))
        env_vars.append(client.V1EnvVar(name="NVIDIA_DRIVER_CAPABILITIES", value="compute,utility"))
    if spec.source_file:
        env_vars.append(client.V1EnvVar(name="PYTHONPATH", value="/opt"))

    for secret in (spec.secrets or []):
        if hasattr(secret, "env_dict"):
            for k, v in secret.env_dict.items():
                env_vars.append(client.V1EnvVar(name=k, value=v))
        elif hasattr(secret, "name") and secret.name:
            import json
            import subprocess

            from openmodal.providers.gcp.config import get_project
            try:
                result = subprocess.run(
                    ["gcloud", "secrets", "versions", "access", "latest",
                     f"--secret={secret.name}", f"--project={get_project()}"],
                    capture_output=True, text=True,
                )
                if result.returncode == 0:
                    secret_data = json.loads(result.stdout)
                    for k, v in secret_data.items():
                        env_vars.append(client.V1EnvVar(name=k, value=v))
            except Exception:
                pass

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


class GKEProvider(CloudProvider):
    def preflight_check(self, spec):
        import shutil
        import subprocess
        if not shutil.which("gcloud"):
            raise RuntimeError("gcloud CLI not found. Run 'openmodal setup gcp' to get started.")
        result = subprocess.run(
            ["gcloud", "config", "get-value", "project"],
            capture_output=True, text=True,
        )
        project = result.stdout.strip() if result.returncode == 0 else ""
        if not project or project == "(unset)":
            raise RuntimeError("No GCP project set. Run: gcloud config set project YOUR_PROJECT_ID")

    def __init__(self):
        # Always point kubectl at our GKE cluster before loading config.
        # Without this, kubectl might be pointing at a different cluster
        # (e.g. an AKS or EKS cluster from a previous session), and pods
        # would be created on the wrong provider.
        self._ensure_gke_context()
        self._v1 = client.CoreV1Api()
        self._apps_v1 = client.AppsV1Api()

    def _ensure_gke_context(self):
        """Make sure kubectl is pointing at our GKE cluster, not some other cluster."""
        import subprocess

        from openmodal.providers.gcp.config import DEFAULT_REGION, get_project
        from openmodal.providers.gcp.gke_setup import CLUSTER_NAME
        project = get_project()
        region = DEFAULT_REGION

        # Check if the cluster exists
        result = subprocess.run(
            ["gcloud", "container", "clusters", "list",
             f"--region={region}", f"--project={project}",
             "--format=value(name)"],
            capture_output=True, text=True,
        )

        if CLUSTER_NAME in result.stdout:
            # Cluster exists — fetch credentials so kubectl points at it
            subprocess.run([
                "gcloud", "container", "clusters", "get-credentials", CLUSTER_NAME,
                f"--region={region}", f"--project={project}",
            ], capture_output=True, check=True)
            config.load_kube_config()
        else:
            # No cluster yet — create one
            self._auto_provision_cluster()
            config.load_kube_config()

    def _auto_provision_cluster(self):
        import logging as _logging

        from openmodal.cli.console import Spinner, success
        from openmodal.providers.gcp.gke_setup import setup_cluster
        _logging.disable(_logging.INFO)
        with Spinner("Creating GKE cluster (one-time, ~5 min)...") as spinner:
            setup_cluster()
        _logging.disable(_logging.NOTSET)
        success(f"GKE cluster ready. ({int(spinner.elapsed)}s)")

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

    def _ensure_default_agent_image(self, source_file: str | None = None) -> str:
        import os

        from openmodal.image import OPENMODAL_PIP_INSTALL, Image
        img = Image.debian_slim()
        img = img._append(OPENMODAL_PIP_INSTALL, "ENV PYTHONPATH=/opt")
        if source_file and os.path.isfile(source_file):
            filename = os.path.basename(source_file)
            img = img._append(f"COPY {filename} /opt/{filename}")
            img._context_files[filename] = source_file
        img = img._append('CMD ["python", "-m", "openmodal.runtime.agent"]')
        return img.build_and_push("default-agent", provider=self)

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
            self._create_idle_scaledown(name, spec.scaledown_window, spec.web_server_port)

        ip = self._wait_for_external_ip(name, timeout=300)
        return name, ip

    def _create_idle_scaledown(self, name: str, scaledown_window: int, port: int):
        # TODO: Replace CronJob hack with KEDA ScaledObject (like AWS/Azure providers).
        # KEDA is already installed on the cluster but we need the right RBAC permissions.
        from kubernetes.client import BatchV1Api

        batch_v1 = BatchV1Api()

        with contextlib.suppress(client.exceptions.ApiException):
            batch_v1.delete_namespaced_cron_job(f"{name}-idle-scaledown", NAMESPACE)

        script = (
            f'DEPLOY={name}; '
            f'NAMESPACE={NAMESPACE}; '
            f'PORT={port}; '
            f'WINDOW={scaledown_window}; '
            'REPLICAS=$(kubectl get deploy $DEPLOY -n $NAMESPACE -o jsonpath="{.spec.replicas}"); '
            'if [ "$REPLICAS" = "0" ]; then exit 0; fi; '
            'POD=$(kubectl get pods -n $NAMESPACE -l app=$DEPLOY -o jsonpath="{.items[0].metadata.name}" 2>/dev/null); '
            'if [ -z "$POD" ]; then exit 0; fi; '
            'READY=$(kubectl get pod $POD -n $NAMESPACE -o '
            'jsonpath="{.status.conditions[?(@.type==\\"Ready\\")].status}" 2>/dev/null); '
            'if [ "$READY" != "True" ]; then exit 0; fi; '
            'LAST=$(kubectl get pod $POD -n $NAMESPACE -o jsonpath="{.metadata.annotations.last-active}" 2>/dev/null); '
            'NOW=$(date +%s); '
            'CONNS=$(kubectl exec $POD -n $NAMESPACE -- '
            'sh -c "ss -tn | grep :$PORT | grep -c ESTAB" 2>/dev/null || echo 0); '
            'if [ "$CONNS" -gt "0" ]; then '
            '  kubectl annotate pod $POD -n $NAMESPACE last-active=$NOW --overwrite; '
            '  exit 0; '
            'fi; '
            'if [ -z "$LAST" ]; then '
            '  kubectl annotate pod $POD -n $NAMESPACE last-active=$NOW --overwrite; '
            '  exit 0; '
            'fi; '
            'IDLE=$((NOW - LAST)); '
            'if [ "$IDLE" -ge "$WINDOW" ]; then '
            '  kubectl scale deploy $DEPLOY -n $NAMESPACE --replicas=0; '
            'fi'
        )

        cronjob = client.V1CronJob(
            metadata=client.V1ObjectMeta(
                name=f"{name}-idle-scaledown",
                labels={"managed-by": LABEL_MANAGED_BY},
            ),
            spec=client.V1CronJobSpec(
                schedule="* * * * *",
                job_template=client.V1JobTemplateSpec(
                    spec=client.V1JobSpec(
                        template=client.V1PodTemplateSpec(
                            spec=client.V1PodSpec(
                                service_account_name="default",
                                restart_policy="Never",
                                containers=[client.V1Container(
                                    name="scaler",
                                    image="bitnami/kubectl:latest",
                                    command=["sh", "-c", script],
                                )],
                            ),
                        ),
                        backoff_limit=0,
                    ),
                ),
            ),
        )

        batch_v1.create_namespaced_cron_job(NAMESPACE, cronjob)

    def _create_pod(self, spec: FunctionSpec, image_uri: str, name: str) -> tuple[str, str]:
        pod = _build_pod_spec(spec, image_uri, name)
        self._v1.create_namespaced_pod(NAMESPACE, pod)
        timeout = 1200 if spec.gpu else 600
        self._wait_for_pod_running(name, timeout=timeout)

        pod_info = self._v1.read_namespaced_pod(name, NAMESPACE)
        ip = pod_info.status.pod_ip
        return name, ip

    def _wait_for_external_ip(self, name: str, timeout: int = 300) -> str:
        start = time.time()
        while time.time() - start < timeout:
            svc = self._v1.read_namespaced_service(name, NAMESPACE)
            ingress = svc.status.load_balancer.ingress
            if ingress and ingress[0].ip:
                return ingress[0].ip
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

        # Timeout — get the reason for the user
        reason = self._get_pod_failure_reason(name)
        raise RuntimeError(f"Pod {name} not ready after {timeout}s: {reason}")

    def _get_pod_failure_reason(self, name: str) -> str:
        """Query pod events and status to produce a human-readable failure reason.

        Events are checked in priority order: mount/permission errors first
        (they indicate the pod scheduled but can't start), then image pull
        errors, then scheduling errors. This avoids returning a stale
        FailedScheduling event when the real problem is a FailedMount.
        """
        try:
            events = self._v1.list_namespaced_event(
                NAMESPACE, field_selector=f"involvedObject.name={name}",
            )

            # Priority 1: Mount/permission errors — pod scheduled but volumes can't attach
            for e in reversed(events.items):
                if e.reason == "FailedMount":
                    msg = e.message or ""
                    if "PermissionDenied" in msg or "403" in msg:
                        return (
                            "Volume mount failed — permission denied. "
                            "The GKE node service account doesn't have access to the storage bucket. "
                            "Re-create the volume or run 'openmodal setup gcp'."
                        )
                    return f"Volume mount failed: {msg}"

            # Priority 2: Image pull errors
            for e in reversed(events.items):
                if e.reason in ("ErrImagePull", "ImagePullBackOff"):
                    return f"Failed to pull container image: {e.message}"

            # Priority 3: Container crash loops
            for e in reversed(events.items):
                if e.reason == "BackOff":
                    return f"Container keeps crashing: {e.message}"

            # Priority 4: Scheduling errors (only if pod never got scheduled)
            pod = self._v1.read_namespaced_pod(name, NAMESPACE)
            if pod.status.phase == "Pending":
                for e in reversed(events.items):
                    if e.reason == "FailedScheduling":
                        msg = e.message or ""
                        if "node affinity" in msg or "nodeSelector" in msg.lower() or "didn't match" in msg:
                            return (
                                "No GPU nodes available. This usually means the GPU node pool "
                                "couldn't scale up — either you don't have quota for this GPU type, "
                                "or spot instances aren't available right now. "
                                "Check your quota: gcloud compute regions describe us-central1 --format='value(quotas)'"
                            )
                        if "insufficient" in msg.lower():
                            return f"Not enough resources to schedule the pod: {msg}"
                        return f"Pod couldn't be scheduled: {msg}"
                return "Pod is still Pending — likely waiting for a GPU node to scale up. Check your quota."

            return f"Pod status: {pod.status.phase}"
        except Exception:
            return "Could not determine reason. Run 'kubectl describe pod' for details."

    def delete_instance(self, instance_name: str) -> None:
        from kubernetes.client import BatchV1Api
        batch_v1 = BatchV1Api()

        # Use default grace period (from pod spec) so the sync-upload
        # sidecar has time to push volume data back to cloud storage.
        for api_call in [
            lambda: self._apps_v1.delete_namespaced_deployment(instance_name, NAMESPACE),
            lambda: self._v1.delete_namespaced_service(instance_name, NAMESPACE),
            lambda: self._v1.delete_namespaced_pod(instance_name, NAMESPACE),
            lambda: batch_v1.delete_namespaced_cron_job(f"{instance_name}-idle-scaledown", NAMESPACE),
        ]:
            with contextlib.suppress(client.exceptions.ApiException):
                api_call()

    def list_instances(self, app_name: str | None = None) -> list[dict]:
        label_selector = f"managed-by={LABEL_MANAGED_BY}"
        if app_name:
            label_selector += f",app={_k8s_name(app_name)}"

        pods = self._v1.list_namespaced_pod(NAMESPACE, label_selector=label_selector)
        results = []
        for pod in pods.items:
            results.append({
                "name": pod.metadata.name,
                "status": pod.status.phase,
                "ip": pod.status.pod_ip or "",
            })
        return results

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

    def machine_spec_str(self, gpu_str: str) -> str:
        return machine_spec_str(
            *self._resolve_machine(gpu_str) if gpu_str else ("e2-small", "", 0)
        )

    def _resolve_machine(self, gpu_str: str) -> tuple[str, str, int]:
        if not gpu_str:
            return "e2-small", "", 0
        machine_type, _, count = parse_gpu_config(gpu_str)
        gpu_name = gpu_str.split(":")[0]
        return machine_type, gpu_name, count

    def instance_name(self, app_name: str, func_name: str, suffix: str = "") -> str:
        return _k8s_name(app_name)

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
            gpu_type, gpu_count = _gpu_node_selector(gpu)
            resources.limits["nvidia.com/gpu"] = str(gpu_count)
            resources.requests["nvidia.com/gpu"] = str(gpu_count)
            node_selector["gpu-type"] = gpu_type
            tolerations.append(client.V1Toleration(
                key="nvidia.com/gpu", operator="Exists", effect="NoSchedule",
            ))
        if cpu:
            resources.requests["cpu"] = str(cpu)
        if memory:
            resources.requests["memory"] = f"{memory}Mi"

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
            stderr=True,
            stdout=True,
            stdin=False,
            tty=False,
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

    def build_image(self, dockerfile_dir: str, name: str, tag: str) -> str:
        """Build and push a container image via GCP. Returns the full image URI."""
        from openmodal.providers.gcp.build import cloud_build
        from openmodal.providers.gcp.config import get_project
        from openmodal.providers.gcp.registry import ensure_repository, get_registry_url

        project = get_project()
        image_uri = get_registry_url(project, name, tag)

        if self.image_exists(image_uri):
            return image_uri

        ensure_repository(project)
        cloud_build(dockerfile_dir, image_uri, project)
        return image_uri

    def image_exists(self, image_uri: str) -> bool:
        """Check whether an image exists in GCP Artifact Registry."""
        import subprocess

        from openmodal.providers.gcp.config import get_project

        project = get_project()
        result = subprocess.run(
            ["gcloud", "artifacts", "docker", "images", "describe", image_uri, "--project", project],
            capture_output=True, text=True,
        )
        return result.returncode == 0

    def stream_logs(self, instance_name: str, *, follow: bool = True,
                    tail: int | None = None, since: str | None = None,
                    include_stderr: bool = False):
        """Stream logs from a Kubernetes pod."""
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

    def ensure_volume(self, name: str) -> str:
        """Ensure a GCS bucket exists for the volume. Returns gs:// URI."""
        from openmodal.providers.gcp.config import get_bucket_name, get_project
        from openmodal.providers.gcp.storage import ensure_bucket

        project = get_project()
        bucket = f"{get_bucket_name(project)}-{name}"
        gs_uri = f"gs://{bucket}"
        ensure_bucket(gs_uri)
        return gs_uri


_provider: GKEProvider | None = None


def get_provider() -> GKEProvider:
    global _provider
    if _provider is None:
        _provider = GKEProvider()
    return _provider
