"""openmodal run — ephemeral deploy, run local entrypoint, tear down."""

from __future__ import annotations

import inspect
import sys

import click

from openmodal.cli import load_app
from openmodal.remote import shutdown_all


def _parse_entrypoint_args(func, extra_args: tuple[str, ...]) -> dict:
    sig = inspect.signature(func)
    params = list(sig.parameters.values())

    if not params:
        return {}

    kwargs = {}
    positional_params = [p for p in params if p.default is inspect.Parameter.empty]
    remaining_args = list(extra_args)

    i = 0
    consumed = set()
    while i < len(remaining_args):
        arg = remaining_args[i]
        if arg.startswith("--"):
            if "=" in arg:
                key, value = arg[2:].split("=", 1)
                kwargs[key.replace("-", "_")] = value
                consumed.add(i)
            elif i + 1 < len(remaining_args) and not remaining_args[i + 1].startswith("--"):
                kwargs[arg[2:].replace("-", "_")] = remaining_args[i + 1]
                consumed.add(i)
                consumed.add(i + 1)
                i += 1
            else:
                kwargs[arg[2:].replace("-", "_")] = True
                consumed.add(i)
        i += 1

    positional_values = [remaining_args[i] for i in range(len(remaining_args)) if i not in consumed]
    for param, value in zip(positional_params, positional_values, strict=False):
        if param.name not in kwargs:
            kwargs[param.name] = value

    for param in params:
        if param.name in kwargs:
            annotation = param.annotation
            if annotation is int:
                kwargs[param.name] = int(kwargs[param.name])
            elif annotation is float:
                kwargs[param.name] = float(kwargs[param.name])
            elif annotation is bool:
                val = kwargs[param.name]
                if isinstance(val, str):
                    kwargs[param.name] = val.lower() in ("true", "1", "yes")

    return kwargs


@click.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
@click.argument("app_path")
@click.pass_context
def run(ctx, app_path: str):
    """Deploy ephemerally, run local_entrypoint, then tear down.

    app_path can be 'file.py' to run the local_entrypoint, or
    'file.py::function_name' to run a specific function.
    """
    target_function = None
    if "::" in app_path:
        app_path, target_function = app_path.rsplit("::", 1)

    app = load_app(app_path)

    click.echo("\u2713 Initialized.")

    deployable = {k: v for k, v in app.functions.items() if v.image is not None and v.web_server_port is not None}
    deployed_funcs: list[str] = []

    if deployable:
        from openmodal.providers import get_provider

        provider = get_provider()

        for func_name, spec in deployable.items():
            spec.image.build_and_push(app.name)
            spec._app_name = app.name
            _, ip = provider.create_instance(spec, spec.image.build_and_push(app.name))
            port = spec.web_server_port or 8000
            url = f"http://{ip}:{port}"
            deployed_funcs.append(func_name)

            if not provider.wait_for_healthy(ip, port, timeout=spec.web_server_startup_timeout):
                raise click.ClickException("Server failed to start")

            user_module = sys.modules.get("_user_app")
            if user_module:
                for attr in dir(user_module):
                    obj = getattr(user_module, attr, None)
                    if hasattr(obj, "_spec") and obj._spec.name == func_name:
                        obj.web_url = url

    click.echo("\u2713 Created objects.")

    try:
        if target_function:
            if target_function not in app.functions:
                raise click.ClickException(
                    f"Function '{target_function}' not found in app. "
                    f"Available: {list(app.functions.keys())}"
                )
            func_spec = app.functions[target_function]
            kwargs = _parse_entrypoint_args(func_spec.func, tuple(ctx.args))
            func_spec.func(**kwargs)
        else:
            for _ep_name, ep_spec in app.local_entrypoints.items():
                kwargs = _parse_entrypoint_args(ep_spec.func, tuple(ctx.args))
                ep_spec.func(**kwargs)
    finally:
        shutdown_all()
        if deployed_funcs:
            from openmodal.providers import get_provider

            provider = get_provider()
            for func_name in deployed_funcs:
                try:
                    name = provider.instance_name(app.name, func_name)
                    provider.delete_instance(name)
                except Exception:
                    pass

    click.echo("\u2713 App completed.")
