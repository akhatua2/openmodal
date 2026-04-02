"""GKE provider — Kubernetes-based compute using the Python kubernetes client."""

from __future__ import annotations

import logging
import time
import urllib.error
import urllib.request

from kubernetes import client, config, watch

from openmodal.function import FunctionSpec
from openmodal.providers.base import CloudProvider
from openmodal.providers.gcp.config import (
    GPU_MAP,
    MACHINE_SPECS,
    machine_spec_str,
    parse_gpu_config,
)

logger = logging.getLogger("openmodal.gke")

NAMESPACE = "default"
LABEL_MANAGED_BY = "openmodal"


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
    if spec.source_file:
        env_vars.append(client.V1EnvVar(name="PYTHONPATH", value="/opt"))

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
                driver="gcsfuse.csi.storage.gke.io",
                volume_attributes={"bucketName": vol.bucket, "mountOptions": "implicit-dirs"},
            ),
        ))
        container.volume_mounts.append(
            client.V1VolumeMount(name=vol_name, mount_path=mount_path),
        )

    return client.V1Pod(
        metadata=client.V1ObjectMeta(
            name=name,
            labels={"app": name, "managed-by": LABEL_MANAGED_BY},
            annotations={"gke-gcsfuse/volumes": "true"} if spec.volumes else None,
        ),
        spec=client.V1PodSpec(
            node_selector=node_selector or None,
            tolerations=tolerations or None,
            containers=[container],
            restart_policy="Never",
            volumes=volumes,
        ),
    )


class GKEProvider(CloudProvider):
    def __init__(self):
        try:
            config.load_kube_config()
        except Exception:
            self._auto_provision_cluster()
            config.load_kube_config()
        self._v1 = client.CoreV1Api()
        self._apps_v1 = client.AppsV1Api()

    def _auto_provision_cluster(self):
        from openmodal.cli.console import Spinner, success
        from openmodal.providers.gcp.gke_setup import setup_cluster, CLUSTER_NAME
        from openmodal.providers.gcp.config import get_project, DEFAULT_ZONE

        import subprocess
        result = subprocess.run(
            ["gcloud", "container", "clusters", "list",
             f"--zone={DEFAULT_ZONE}", f"--project={get_project()}",
             "--format=value(name)"],
            capture_output=True, text=True,
        )
        if CLUSTER_NAME in result.stdout:
            subprocess.run([
                "gcloud", "container", "clusters", "get-credentials", CLUSTER_NAME,
                f"--zone={DEFAULT_ZONE}", f"--project={get_project()}",
            ], capture_output=True, check=True)
            return

        with Spinner("Creating GKE cluster (one-time, ~5 min)...") as spinner:
            setup_cluster()
        success(f"GKE cluster ready. ({int(spinner.elapsed)}s)")

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

        try:
            self._apps_v1.delete_namespaced_deployment(name, NAMESPACE)
            time.sleep(2)
        except client.exceptions.ApiException:
            pass

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

        try:
            self._v1.delete_namespaced_service(name, NAMESPACE)
            time.sleep(1)
        except client.exceptions.ApiException:
            pass

        self._v1.create_namespaced_service(NAMESPACE, service)

        ip = self._wait_for_external_ip(name, timeout=300)
        return name, ip

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
            if pod.status.phase == "Running":
                w.stop()
                return
            if pod.status.phase in ("Failed", "Unknown"):
                w.stop()
                raise RuntimeError(f"Pod {name} entered {pod.status.phase} state")

    def delete_instance(self, instance_name: str) -> None:
        try:
            self._apps_v1.delete_namespaced_deployment(instance_name, NAMESPACE)
        except client.exceptions.ApiException:
            pass
        try:
            self._v1.delete_namespaced_service(instance_name, NAMESPACE)
        except client.exceptions.ApiException:
            pass
        try:
            self._v1.delete_namespaced_pod(
                instance_name, NAMESPACE,
                body=client.V1DeleteOptions(grace_period_seconds=0),
            )
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


_provider: GKEProvider | None = None


def get_provider() -> GKEProvider:
    global _provider
    if _provider is None:
        _provider = GKEProvider()
    return _provider
