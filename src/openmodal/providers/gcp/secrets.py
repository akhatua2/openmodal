"""GCP Secret Manager operations."""

from __future__ import annotations

from openmodal.secret import Secret


def fetch_script(secret: Secret) -> str:
    """Shell commands to fetch a secret from GCP Secret Manager and export as env vars.

    The secret value is expected to be a JSON object whose keys become env var names.
    """
    return (
        f'SECRET_VALUE=$(gcloud secrets versions access latest --secret="{secret.name}" 2>/dev/null)\n'
        f'if [ -n "$SECRET_VALUE" ]; then\n'
        f'  for key in $(echo "$SECRET_VALUE" | python3 -c "import sys,json; print(\'\\n\'.join(json.load(sys.stdin).keys()))"); do\n'
        f'    val=$(echo "$SECRET_VALUE" | python3 -c "import sys,json; print(json.load(sys.stdin)[\'$key\'])")\n'
        f'    export "$key=$val"\n'
        f'  done\n'
        f'fi\n'
    )


def secrets_script(secrets: list[Secret]) -> str:
    """Combined fetch script for multiple secrets."""
    return "".join(fetch_script(s) for s in secrets)
