"""AWS EKS provider — Kubernetes-based compute on AWS with Karpenter and KEDA."""

from __future__ import annotations

import logging
import time
import urllib.error
import urllib.request

from kubernetes import client, config, watch

from openmodal.function import FunctionSpec
from openmodal.providers.base import CloudProvider
from openmodal.providers.aws.config import (
    GPU_MAP,
    MACHINE_SPECS,
    machine_spec_str,
    parse_gpu_config,
    get_account_id,
    get_region,
)

logger = logging.getLogger("openmodal.aws.eks")

NAMESPACE = "default"
LABEL_MANAGED_BY = "openmodal"


def _k8s_name(name: str) -> str:
    return name.lower().replace("_", "-")[:63]


def _gpu_node_selector(gpu_str: str) -> tuple[str, int]:
    """Returns (instance_type, gpu count) for Karpenter scheduling."""
    parts = gpu_str.replace("!", "").split(":")
    gpu_name = parts[0].upper()
    count = int(parts[1]) if len(parts) > 1 else 1

    if gpu_name not in GPU_MAP:
        raise ValueError(f"Unknown GPU: {gpu_name}. Available: {list(GPU_MAP.keys())}")

    _, instance_type, _ = GPU_MAP[gpu_name]
    return instance_type, count


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
        instance_type, gpu_count = _gpu_node_selector(spec.gpu)
        resources.limits["nvidia.com/gpu"] = str(gpu_count)
        resources.requests["nvidia.com/gpu"] = str(gpu_count)
        # Karpenter picks the right instance type based on resource requests
        # but we can hint with a node selector for specific instance types
        node_selector["node.kubernetes.io/instance-type"] = instance_type
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

    for mount_path, vol in spec.volumes.items():
        vol_name = f"vol-{vol.name}"
        volumes.append(client.V1Volume(
            name=vol_name,
            csi=client.V1CSIVolumeSource(
                driver="s3.csi.aws.com",
                volume_attributes={"bucketName": vol.bucket},
            ),
        ))
        container.volume_mounts.append(
            client.V1VolumeMount(name=vol_name, mount_path=mount_path),
        )

    return client.V1Pod(
        metadata=client.V1ObjectMeta(
            name=name,
            labels={"app": name, "managed-by": LABEL_MANAGED_BY},
        ),
        spec=client.V1PodSpec(
            node_selector=node_selector or None,
            tolerations=tolerations or None,
            containers=[container],
            restart_policy="Never",
            volumes=volumes,
        ),
    )


class EKSProvider(CloudProvider):
    def __init__(self):
        try:
            config.load_kube_config()
            # Verify we can reach the cluster
            client.CoreV1Api().list_namespace(limit=1)
        except Exception:
            self._auto_provision_cluster()
            config.load_kube_config()
        self._v1 = client.CoreV1Api()
        self._apps_v1 = client.AppsV1Api()

    def _auto_provision_cluster(self):
        from openmodal.cli.console import Spinner, success
        from openmodal.providers.aws.eks_setup import cluster_exists, update_kubeconfig, setup_cluster

        if cluster_exists():
            update_kubeconfig()
            return

        with Spinner("Creating EKS cluster (one-time, ~15 min)...") as spinner:
            setup_cluster()
        success(f"EKS cluster ready. ({int(spinner.elapsed)}s)")

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

    # ── Core instance management ──────────────────────────────────────

    def create_instance(
        self, spec: FunctionSpec, image_uri: str | None = None, name: str | None = None,
    ) -> tuple[str, str]:
        name = name or _k8s_name(getattr(spec, "_app_name", "app"))
        image_uri = image_uri or ""

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

        if spec.scaledown_window > 0:
            self._create_keda_scaledown(name, spec.scaledown_window, spec.web_server_port)

        ip = self._wait_for_external_ip(name, timeout=300)
        return name, ip

    def _create_keda_scaledown(self, name: str, scaledown_window: int, port: int):
        """Create a KEDA ScaledObject for scale-to-zero based on idle connections."""
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
                "fallback": {
                    "failureThreshold": 3,
                    "replicas": 1,
                },
            },
        }

        try:
            custom.delete_namespaced_custom_object(
                "keda.sh", "v1alpha1", NAMESPACE, "scaledobjects", f"{name}-scaledown",
            )
        except client.exceptions.ApiException:
            pass

        custom.create_namespaced_custom_object(
            "keda.sh", "v1alpha1", NAMESPACE, "scaledobjects", scaled_object,
        )

    def _create_pod(self, spec: FunctionSpec, image_uri: str, name: str) -> tuple[str, str]:
        pod = _build_pod_spec(spec, image_uri, name)

        try:
            self._v1.delete_namespaced_pod(name, NAMESPACE, grace_period_seconds=0)
            time.sleep(2)
        except client.exceptions.ApiException:
            pass

        self._v1.create_namespaced_pod(NAMESPACE, pod)
        self._wait_for_pod_running(name)

        pod_info = self._v1.read_namespaced_pod(name, NAMESPACE)
        ip = pod_info.status.pod_ip
        return name, ip

    def _wait_for_external_ip(self, name: str, timeout: int = 300) -> str:
        """Wait for LoadBalancer to get an external IP/hostname."""
        start = time.time()
        while time.time() - start < timeout:
            svc = self._v1.read_namespaced_service(name, NAMESPACE)
            ingress = svc.status.load_balancer.ingress
            if ingress:
                # AWS NLB gives hostname, not IP
                return ingress[0].hostname or ingress[0].ip
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
            if pod.status.phase == "Running" and pod.status.pod_ip:
                if pod.status.container_statuses and all(
                    cs.ready or (cs.state and cs.state.running) for cs in pod.status.container_statuses
                ):
                    w.stop()
                    return
            if pod.status.phase in ("Failed", "Unknown"):
                w.stop()
                raise RuntimeError(f"Pod {name} entered {pod.status.phase} state")

    def delete_instance(self, instance_name: str) -> None:
        from kubernetes.client import BatchV1Api, CustomObjectsApi
        batch_v1 = BatchV1Api()
        custom = CustomObjectsApi()

        for api_call in [
            lambda: self._apps_v1.delete_namespaced_deployment(instance_name, NAMESPACE),
            lambda: self._v1.delete_namespaced_service(instance_name, NAMESPACE),
            lambda: self._v1.delete_namespaced_pod(instance_name, NAMESPACE, body=client.V1DeleteOptions(grace_period_seconds=0)),
            lambda: batch_v1.delete_namespaced_cron_job(f"{instance_name}-idle-scaledown", NAMESPACE),
            lambda: custom.delete_namespaced_custom_object(
                "keda.sh", "v1alpha1", NAMESPACE, "scaledobjects", f"{instance_name}-scaledown",
            ),
        ]:
            try:
                api_call()
            except client.exceptions.ApiException:
                pass

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

    # ── Machine specs ─────────────────────────────────────────────────

    def machine_spec_str(self, gpu_str: str) -> str:
        if not gpu_str:
            return "t3.medium"
        instance_type, gpu_name, count = parse_gpu_config(gpu_str)
        return machine_spec_str(instance_type, gpu_name, count)

    def instance_name(self, app_name: str, func_name: str, suffix: str = "") -> str:
        return _k8s_name(app_name)

    # ── Sandboxes ─────────────────────────────────────────────────────

    def create_sandbox_pod(
        self, name: str, image_uri: str | None, timeout: int = 3600,
        gpu: str | None = None, cpu: float | None = None, memory: int | None = None,
        env_vars: dict[str, str] | None = None,
    ):
        try:
            self._v1.delete_namespaced_pod(name, NAMESPACE, grace_period_seconds=0)
            time.sleep(2)
        except client.exceptions.ApiException:
            pass

        image = image_uri or "ubuntu:24.04"

        resources = client.V1ResourceRequirements(requests={}, limits={})
        node_selector = {}
        tolerations = []

        if gpu:
            instance_type, gpu_count = _gpu_node_selector(gpu)
            resources.limits["nvidia.com/gpu"] = str(gpu_count)
            resources.requests["nvidia.com/gpu"] = str(gpu_count)
            node_selector["node.kubernetes.io/instance-type"] = instance_type
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

    def exec_in_pod(self, pod_name: str, *args: str, workdir: str | None = None, env: dict[str, str] | None = None):
        from kubernetes.stream import stream
        from openmodal.process import ContainerProcess

        command = list(args)
        if workdir and command[0] == "bash" and "-c" in command:
            idx = command.index("-c")
            if idx + 1 < len(command):
                command[idx + 1] = f"cd {workdir} && {command[idx + 1]}"
        elif workdir:
            command = ["bash", "-c", f"cd {workdir} && {' '.join(command)}"]

        if env:
            if command[0] == "bash" and "-c" in command:
                idx = command.index("-c")
                if idx + 1 < len(command):
                    prefix = " ".join(f"export {k}={v};" for k, v in env.items())
                    command[idx + 1] = f"{prefix} {command[idx + 1]}"

        resp = stream(
            self._v1.connect_get_namespaced_pod_exec,
            name=pod_name,
            namespace=NAMESPACE,
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

    # ── Images ────────────────────────────────────────────────────────

    def build_image(self, dockerfile_dir: str, name: str, tag: str) -> str:
        from openmodal.providers.aws.ecr import get_registry_url, ensure_repository, docker_login
        from openmodal.providers.aws.build import build_and_push

        account_id = get_account_id()
        region = get_region()
        image_uri = get_registry_url(account_id, region, name, tag)

        if self.image_exists(image_uri):
            return image_uri

        ensure_repository(account_id, region, name)
        docker_login(account_id, region)
        build_and_push(dockerfile_dir, image_uri)
        return image_uri

    def image_exists(self, image_uri: str) -> bool:
        import boto3
        # Parse image URI: account.dkr.ecr.region.amazonaws.com/name:tag
        try:
            repo_and_tag = image_uri.split("/", 1)[1]  # name:tag
            repo_name, tag = repo_and_tag.rsplit(":", 1)
            region = get_region()
            ecr = boto3.client("ecr", region_name=region)
            ecr.describe_images(
                repositoryName=repo_name,
                imageIds=[{"imageTag": tag}],
            )
            return True
        except Exception:
            return False

    # ── Volumes ───────────────────────────────────────────────────────

    def ensure_volume(self, name: str) -> str:
        from openmodal.providers.aws.s3 import ensure_bucket

        account_id = get_account_id()
        region = get_region()
        bucket_name = f"openmodal-{account_id}-{name}"
        ensure_bucket(bucket_name, region)
        return f"s3://{bucket_name}"

    # ── Logs ──────────────────────────────────────────────────────────

    def stream_logs(self, instance_name: str):
        import subprocess, sys
        try:
            return subprocess.Popen(
                ["kubectl", "logs", "-f", instance_name, "-n", NAMESPACE, "-c", "main"],
                stdout=sys.stdout, stderr=subprocess.DEVNULL,
            )
        except Exception:
            return None
