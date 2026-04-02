"""VM startup script template — runs inside the GCE VM on boot."""

from __future__ import annotations

_TEMPLATE = """\
#!/bin/bash
set -ex

# Docker
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
fi

# gcsfuse
if ! command -v gcsfuse &>/dev/null; then
    export GCSFUSE_REPO=gcsfuse-$(lsb_release -c -s)
    echo "deb [signed-by=/usr/share/keyrings/cloud.google.asc] https://packages.cloud.google.com/apt $GCSFUSE_REPO main" \
        | tee /etc/apt/sources.list.d/gcsfuse.list
    curl https://packages.cloud.google.com/apt/doc/apt-key.gpg \
        | tee /usr/share/keyrings/cloud.google.asc
    apt-get update && apt-get install -y gcsfuse
fi

# NVIDIA Container Toolkit
if ! dpkg -l | grep -q nvidia-container-toolkit; then
    distribution=$(. /etc/os-release; echo $ID$VERSION_ID)
    curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
        | gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
    curl -s -L "https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list" \
        | sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' \
        | tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
    apt-get update && apt-get install -y nvidia-container-toolkit
    nvidia-ctk runtime configure --runtime=docker
    systemctl restart docker
fi

# Auth with Artifact Registry
gcloud auth configure-docker {registry_host} --quiet

# Mount volumes
{volume_commands}

# Pull and run
docker pull {image_uri}
docker run -d --name openmodal-serve \\
    --gpus all --network host --shm-size=16g \\
    {volume_mounts} \\
    {image_uri}

# Idle watchdog — self-delete after scaledown_window of inactivity
cat > /opt/idle-watchdog.sh << 'WATCHDOG'
#!/bin/bash
SCALEDOWN={scaledown_window}
PORT={port}
LAST_ACTIVE=$(date +%s)

while true; do
    CONNECTIONS=$(ss -tnp | grep ":$PORT" | grep -c ESTAB || true)
    NOW=$(date +%s)
    if [ "$CONNECTIONS" -gt 0 ]; then
        LAST_ACTIVE=$NOW
    fi
    IDLE=$((NOW - LAST_ACTIVE))
    if [ "$IDLE" -ge "$SCALEDOWN" ]; then
        ZONE=$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/zone | cut -d/ -f4)
        NAME=$(curl -sf -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/name)
        gcloud compute instances delete "$NAME" --zone="$ZONE" --quiet
        exit 0
    fi
    sleep 30
done
WATCHDOG
chmod +x /opt/idle-watchdog.sh
nohup /opt/idle-watchdog.sh &>/var/log/idle-watchdog.log &
"""


def render_startup_script(
    *,
    image_uri: str,
    volume_commands: list[str],
    docker_volume_mounts: list[str],
    scaledown_window: int,
    port: int,
) -> str:
    registry_host = image_uri.split("/")[0]
    return _TEMPLATE.format(
        registry_host=registry_host,
        image_uri=image_uri,
        volume_commands="\n".join(volume_commands),
        volume_mounts=" \\\n    ".join(docker_volume_mounts),
        scaledown_window=scaledown_window,
        port=port,
    )
