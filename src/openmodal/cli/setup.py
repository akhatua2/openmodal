"""Interactive provider setup — guides users through configuration."""

from __future__ import annotations

import json
import shutil
import subprocess

import click

from openmodal.cli.prompt import BOLD, DIM, RESET, confirm, done, header, select, step_fail, step_hint, step_ok


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def _has(name: str) -> bool:
    return shutil.which(name) is not None


def _need(name: str, url: str) -> bool:
    if _has(name):
        step_ok(f"{name} is installed")
        return True
    step_fail(f"{name} is not installed")
    step_hint(f"Install: {url}")
    return False


@click.group(invoke_without_command=True)
@click.pass_context
def setup(ctx):
    """Set up a cloud provider for OpenModal."""
    if ctx.invoked_subcommand is not None:
        return

    provider = select("Which provider do you want to set up?", [
        "Local (Docker)",
        "GCP",
        "AWS",
        "Azure",
        "Cluster (SSH)",
    ])

    cmd_map = {"Local (Docker)": local, "GCP": gcp, "AWS": aws, "Azure": azure, "Cluster (SSH)": cluster}
    ctx.invoke(cmd_map[provider])


@setup.command()
def local():
    """Set up local Docker provider."""
    header("Setting up Docker")

    if not _need("docker", "https://docs.docker.com/get-docker/"):
        return

    result = _run(["docker", "info"])
    if result.returncode != 0:
        step_fail("Docker daemon isn't running")
        step_hint("Start it: sudo systemctl start docker")
        return
    step_ok("Docker daemon is running")

    result = _run(["docker", "run", "--rm", "hello-world"])
    if result.returncode != 0:
        step_fail("Docker needs sudo")
        step_hint("Fix: sudo usermod -aG docker $USER && newgrp docker")
        return
    step_ok("Docker works without sudo")

    done("You're all set! Try: openmodal --local run examples/hello_world.py")


@setup.command()
def gcp():
    """Set up GCP provider."""
    header("Setting up GCP")

    if not _need("gcloud", "https://cloud.google.com/sdk/docs/install"):
        return
    if not _has("kubectl"):
        step_fail("kubectl is not installed")
        if confirm("Install kubectl via gcloud?"):
            _run(["gcloud", "components", "install", "kubectl", "--quiet"])
            if _has("kubectl"):
                step_ok("kubectl installed")
            else:
                step_fail("Install failed — try manually: https://kubernetes.io/docs/tasks/tools/")
                return
        else:
            return
    else:
        step_ok("kubectl is installed")

    if not _has("gke-gcloud-auth-plugin"):
        step_fail("gke-gcloud-auth-plugin is not installed")
        if confirm("Install it via gcloud?"):
            _run(["gcloud", "components", "install", "gke-gcloud-auth-plugin", "--quiet"])
            if _has("gke-gcloud-auth-plugin"):
                step_ok("gke-gcloud-auth-plugin installed")
            else:
                step_fail("Install failed — try manually: gcloud components install gke-gcloud-auth-plugin")
                return
        else:
            return
    else:
        step_ok("gke-gcloud-auth-plugin is installed")

    # Auth
    result = _run(["gcloud", "auth", "list", "--filter=status:ACTIVE", "--format=value(account)"])
    account = result.stdout.strip() if result.returncode == 0 else ""
    if not account:
        step_fail("Not logged in")
        step_hint("Run: gcloud auth login")
        return
    step_ok(f"Logged in as {account}")

    # Project selection
    result = _run(["gcloud", "projects", "list", "--format=value(projectId)", "--sort-by=projectId"])
    if result.returncode == 0 and result.stdout.strip():
        projects = [p for p in result.stdout.strip().split("\n") if p]
        if len(projects) > 1:
            project = select("Which project?", projects)
            _run(["gcloud", "config", "set", "project", project])
        else:
            project = projects[0]
        step_ok(f"Using project {project}")
    else:
        step_fail("No projects found")
        step_hint("Create one: gcloud projects create my-project")
        return

    # APIs
    result = _run(["gcloud", "services", "list", "--enabled", "--format=value(config.name)", "--project", project])
    enabled = set(result.stdout.strip().split("\n")) if result.returncode == 0 else set()

    required = {
        "compute.googleapis.com": "Compute Engine",
        "container.googleapis.com": "Kubernetes Engine",
        "cloudbuild.googleapis.com": "Cloud Build",
        "artifactregistry.googleapis.com": "Artifact Registry",
    }

    missing = []
    for api, label in required.items():
        if api in enabled:
            step_ok(label)
        else:
            step_fail(label)
            missing.append(api)

    if missing:
        if confirm("Enable missing APIs?"):
            result = _run(["gcloud", "services", "enable", *missing, "--project", project])
            if result.returncode == 0:
                step_ok("APIs enabled")
            else:
                step_fail(f"Failed: {result.stderr.strip()}")
                return
        else:
            return

    done("You're all set! Try: openmodal run examples/hello_world.py")


@setup.command()
def aws():
    """Set up AWS provider."""
    header("Setting up AWS")

    ok = True
    ok &= _need("aws", "https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html")
    ok &= _need("eksctl", "https://eksctl.io/installation/")
    ok &= _need("helm", "https://helm.sh/docs/intro/install/")
    ok &= _need("docker", "https://docs.docker.com/get-docker/")

    if not _has("aws") or not ok:
        return

    # Auth
    result = _run(["aws", "sts", "get-caller-identity"])
    if result.returncode != 0:
        step_fail("Not authenticated")
        if confirm("Log in now?"):
            import subprocess
            subprocess.run(["aws", "login"])
            result = _run(["aws", "sts", "get-caller-identity"])
            if result.returncode != 0:
                step_fail("Login failed")
                return
        else:
            return
    identity = json.loads(result.stdout)
    step_ok(f"Logged in as {identity.get('Arn', 'unknown')}")

    # Region
    result = _run(["aws", "configure", "get", "region"])
    region = result.stdout.strip() if result.returncode == 0 else ""
    if not region:
        regions = ["us-east-1", "us-west-2", "eu-west-1", "ap-southeast-1"]
        region = select("Which region?", regions)
        _run(["aws", "configure", "set", "region", region])
    step_ok(f"Region: {region}")

    # Extras
    try:
        import boto3  # noqa: F401
        step_ok("openmodal[aws] installed")
    except ImportError:
        step_fail("openmodal[aws] not installed")
        step_hint('Run: pip install "openmodal[aws]"')
        return

    done("You're all set! Try: openmodal --aws run examples/hello_world.py")


@setup.command()
def azure():
    """Set up Azure provider."""
    header("Setting up Azure")

    if not _need("az", "https://learn.microsoft.com/en-us/cli/azure/install-azure-cli"):
        return
    _need("docker", "https://docs.docker.com/get-docker/")

    # Auth
    result = _run(["az", "account", "show"])
    if result.returncode != 0:
        step_fail("Not logged in")
        step_hint("Run: az login")
        return

    # Subscription selection
    result = _run(["az", "account", "list", "--query", "[].{name:name, id:id}", "-o", "json"])
    if result.returncode == 0:
        subs = json.loads(result.stdout)
        if len(subs) > 1:
            choices = [f"{s['name']} ({s['id'][:8]}…)" for s in subs]
            choice = select("Which subscription?", choices)
            idx = choices.index(choice)
            _run(["az", "account", "set", "--subscription", subs[idx]["id"]])
            step_ok(f"Using {subs[idx]['name']}")
        elif subs:
            step_ok(f"Using {subs[0]['name']}")
        else:
            step_fail("No subscriptions found")
            return
    else:
        step_fail("Couldn't list subscriptions")
        return

    # Resource providers
    required = {
        "Microsoft.ContainerService": "Container Service (AKS)",
        "Microsoft.ContainerRegistry": "Container Registry (ACR)",
        "Microsoft.Storage": "Storage",
    }

    missing = []
    for namespace, label in required.items():
        result = _run(["az", "provider", "show", "--namespace", namespace, "--query", "registrationState", "-o", "tsv"])
        if result.returncode == 0 and "Registered" in result.stdout:
            step_ok(label)
        else:
            step_fail(label)
            missing.append(namespace)

    if missing:
        if confirm("Register missing providers?"):
            for ns in missing:
                _run(["az", "provider", "register", "--namespace", ns])
            step_ok("Registration started (may take a minute)")
        else:
            return

    done("You're all set! Try: openmodal --azure run examples/hello_world.py")


@setup.command()
def cluster():
    """Set up an SSH cluster provider (no Docker, no SLURM)."""
    header("Setting up SSH Cluster")

    if not _need("ssh", "SSH should be pre-installed on your system"):
        return

    # Collect nodes
    click.echo(f"  {BOLD}Enter SSH host aliases{RESET} (must match ~/.ssh/config entries)")
    click.echo(f"  {DIM}Comma-separated, e.g.: ampere1,ampere2,ampere3{RESET}")
    nodes_input = click.prompt("  Nodes", type=str)
    nodes = [n.strip() for n in nodes_input.split(",") if n.strip()]

    if not nodes:
        step_fail("No nodes provided")
        return

    # Test SSH to each node
    reachable = []
    for node in nodes:
        result = _run(["ssh", "-O", "check", node])
        if result.returncode == 0:
            step_ok(f"{node} — connected")
            reachable.append(node)
        else:
            # Try a quick connect
            result = _run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=5", node, "hostname"])
            if result.returncode == 0:
                step_ok(f"{node} — connected")
                reachable.append(node)
            else:
                step_fail(f"{node} — cannot connect (open a session first: ssh {node})")

    if not reachable:
        step_fail("No reachable nodes. Connect to at least one node first.")
        return

    # Pick default node
    if len(reachable) > 1:
        default_node = select("Default node?", reachable)
    else:
        default_node = reachable[0]
    step_ok(f"Default node: {default_node}")

    # Remote working directory
    click.echo(f"\n  {BOLD}Remote working directory{RESET}")
    click.echo(f"  {DIM}Where OpenModal stores envs, code, logs on the cluster.{RESET}")
    click.echo(f"  {DIM}Use a shared filesystem if nodes share storage.{RESET}")
    remote_base = click.prompt("  Path", type=str, default="~/.openmodal")
    step_ok(f"Remote base: {remote_base}")

    # Env setup script (optional)
    click.echo(f"\n  {BOLD}Environment setup script{RESET} {DIM}(optional){RESET}")
    click.echo(f"  {DIM}Sourced before every command. Sets up PATH, caches, conda, etc.{RESET}")
    env_script = click.prompt("  Script path (or 'none')", type=str, default="none")
    if env_script.lower() == "none":
        env_script = None
    else:
        step_ok(f"Env script: {env_script}")

    # Check for uv on the default node
    result = _run(["ssh", "-o", "BatchMode=yes", default_node, "bash -lc 'which uv'"])
    if result.returncode == 0:
        step_ok("uv is available on the cluster")
    else:
        # Try with env script
        if env_script:
            result = _run(["ssh", "-o", "BatchMode=yes", default_node, f"source {env_script} && which uv"])
        if result.returncode != 0:
            step_fail("uv is not available on the cluster")
            step_hint("Install: curl -LsSf https://astral.sh/uv/install.sh | sh")
            return

    # Save config
    from openmodal.providers.cluster.config import save_config
    save_config({
        "nodes": reachable,
        "default_node": default_node,
        "remote_base": remote_base,
        "env_setup_script": env_script,
    })
    step_ok("Config saved to ~/.openmodal/cluster.json")

    # Create remote directories
    subdirs = " ".join(f"{remote_base}/{d}" for d in ("envs", "logs", "pids", "code", "volumes"))
    result = _run(["ssh", "-o", "BatchMode=yes", default_node, f"mkdir -p {subdirs}"])
    if result.returncode == 0:
        step_ok("Remote directories created")
    else:
        step_fail(f"Could not create remote directories: {result.stderr.strip()}")

    done(f"You're all set! Try: openmodal --cluster run examples/hello_world.py")
