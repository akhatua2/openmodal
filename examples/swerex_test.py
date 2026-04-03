"""Test SWE-Rex integration with OpenModal sandboxes.

Runs swerex-server in a sandbox and connects a RemoteRuntime to it.
"""

import asyncio
import openmodal

app = openmodal.App("swerex-test")

swerex_image = openmodal.Image.debian_slim().apt_install("git").run_commands(
    "pip install pipx",
    "pipx ensurepath",
    "pipx install swe-rex",
)


async def run():
    from swerex.deployment.abstract import AbstractDeployment
    from swerex.runtime.remote import RemoteRuntime
    from swerex.utils.wait import _wait_until_alive

    sandbox = openmodal.Sandbox.create(image=swerex_image, app=app, timeout=600)
    print(f"Sandbox created: {sandbox.id}")

    port = 8880
    token = "test-token-123"
    sandbox.exec(f"nohup swerex --port {port} --auth-token {token} > /tmp/swerex.log 2>&1 &")

    import time
    time.sleep(3)

    pod_ip = sandbox._provider._v1.read_namespaced_pod(sandbox.id, "default").status.pod_ip
    print(f"Pod IP: {pod_ip}")

    runtime = RemoteRuntime(host=f"http://{pod_ip}:{port}", auth_token=token, timeout=30.0)

    async def check_alive(timeout=None):
        return await runtime.is_alive(timeout=timeout)

    await _wait_until_alive(check_alive, timeout=30.0, function_timeout=5.0)
    print("Runtime is alive!")

    result = await runtime.execute("echo 'Hello from swerex!'")
    print(f"Output: {result.output}")

    result = await runtime.execute("python3 --version")
    print(f"Python: {result.output}")

    result = await runtime.execute("git --version")
    print(f"Git: {result.output}")

    await runtime.close()
    sandbox.terminate()
    print("Done!")


@app.local_entrypoint()
def main():
    asyncio.run(run())
