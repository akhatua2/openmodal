"""Shared volume pod spec builder — creates init containers, sidecars, and emptyDir volumes.

All cloud providers use the same pattern: sync data from cloud storage into an emptyDir
at startup (init container), and sync it back on shutdown (sidecar). The only difference
is the CLI image used for syncing (gcloud, aws, az).
"""

from __future__ import annotations

from kubernetes import client

from openmodal.function import FunctionSpec


def build_volume_specs(
    spec: FunctionSpec,
    sync_image: str,
) -> tuple[list, list, list, list]:
    """Build Kubernetes volume specs for cloud storage sync.

    Returns:
        (volumes, main_volume_mounts, init_containers, sidecar_containers)
    """
    volumes = []
    main_mounts = []
    init_containers = []
    sync_up_commands = []

    for mount_path, vol in spec.volumes.items():
        vol_name = f"vol-{vol.name}"

        volumes.append(client.V1Volume(
            name=vol_name,
            empty_dir=client.V1EmptyDirVolumeSource(),
        ))

        main_mounts.append(
            client.V1VolumeMount(name=vol_name, mount_path=mount_path),
        )

        init_containers.append(client.V1Container(
            name=f"sync-down-{vol.name}",
            image=sync_image,
            command=["sh", "-c", vol.sync_down_command(mount_path)],
            volume_mounts=[client.V1VolumeMount(name=vol_name, mount_path=mount_path)],
        ))

        sync_up_commands.append(vol.sync_up_command(mount_path))

    sidecar_containers = []
    if sync_up_commands:
        upload_script = " && ".join(sync_up_commands)
        sidecar_containers.append(client.V1Container(
            name="sync-upload",
            image=sync_image,
            command=["sh", "-c", f"trap '{upload_script}' TERM; sleep infinity"],
            volume_mounts=[
                client.V1VolumeMount(name=f"vol-{vol.name}", mount_path=mp)
                for mp, vol in spec.volumes.items()
            ],
        ))

    return volumes, main_mounts, init_containers, sidecar_containers
