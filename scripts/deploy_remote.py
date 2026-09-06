"""Inspect and optionally restart the Pi capture service without exposing secrets."""

from __future__ import annotations

import argparse
import shlex
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from firmware.sticks3.scripts.generate_config import parse_env_file


@dataclass(frozen=True)
class DeploymentConfig:
    host: str
    user: str
    project_dir: str
    ssh_password: str
    artifact_dir: str
    remote_token: str


def _required(values: Mapping[str, str], key: str) -> str:
    value = values.get(key, "")
    if not value:
        raise ValueError(f"missing required {key} in local env file")
    return value


def deployment_config(values: Mapping[str, str]) -> DeploymentConfig:
    return DeploymentConfig(
        host=_required(values, "PI_HOST"),
        user=_required(values, "PI_USER"),
        project_dir=_required(values, "PI_PROJECT_DIR"),
        ssh_password=_required(values, "PI_SSH_PASSWORD"),
        artifact_dir=_required(values, "PI_ARTIFACT_DIR"),
        remote_token=_required(values, "PARR_REMOTE_TOKEN"),
    )


def build_capture_command(config: DeploymentConfig, *, show_captures: bool) -> str:
    """Build the command only after its artifact directory has been inspected."""
    parts = [
        f"{config.project_dir}/.venv/bin/parr-capture",
        "--no-preview",
    ]
    if show_captures:
        parts.append("--show-captures")
    parts.extend(
        [
            "--remote-listen",
            f"{config.host}:8765",
            "--artifacts",
            config.artifact_dir,
        ]
    )
    return shlex.join(parts)


def open_ssh_client(config: DeploymentConfig, *, paramiko_module: Any | None = None) -> Any:
    """Open password SSH only when the host is already trusted locally."""
    if paramiko_module is None:
        try:
            import paramiko as paramiko_module
        except ImportError as error:
            message = "install deployment support with: pip install -e '.[deploy]'"
            raise RuntimeError(message) from error
    client = paramiko_module.SSHClient()
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko_module.RejectPolicy())
    client.connect(
        hostname=config.host,
        username=config.user,
        password=config.ssh_password,
        look_for_keys=False,
        allow_agent=False,
        timeout=15,
    )
    return client


def inspection_commands(config: DeploymentConfig) -> list[tuple[str, str]]:
    project = shlex.quote(config.project_dir)
    artifact = shlex.quote(config.artifact_dir)
    return [
        ("project", f"test -d {project}"),
        (
            "artifact",
            f"test -d {artifact} && test -f {artifact}/params.json && test -f {artifact}/parr.cube",
        ),
        ("capture process", "pgrep -af '[p]arr-capture' || true"),
        ("camera owners", "fuser -v /dev/video* 2>/dev/null || true"),
        ("desktop session", "loginctl list-sessions --no-legend 2>/dev/null || true"),
    ]


def _run(client: Any, command: str) -> tuple[int, str, str]:
    _stdin, stdout, stderr = client.exec_command(command)
    return stdout.channel.recv_exit_status(), stdout.read().decode(), stderr.read().decode()


def inspect_target(client: Any, config: DeploymentConfig) -> dict[str, str]:
    results: dict[str, str] = {}
    for label, command in inspection_commands(config):
        status, output, error = _run(client, command)
        if status:
            detail = error.strip() or "command failed"
            raise RuntimeError(f"Pi inspection failed for {label}: {detail}")
        results[label] = output.strip()
    return results


def restart_headless_service(client: Any, inspection: Mapping[str, str]) -> None:
    """Stop first, then refuse to start while any process still owns a camera."""
    # The initial inspection may correctly find the service we are replacing.
    # Stop it first, then inspect again before starting a replacement.
    status, _output, error = _run(client, "sudo -n systemctl stop parr-capture.service")
    if status:
        detail = error.strip() or "command failed"
        raise RuntimeError(f"could not stop parr-capture.service: {detail}")
    status, process_output, _error = _run(client, "pgrep -af '[p]arr-capture' || true")
    if status or process_output.strip():
        raise RuntimeError("refusing restart: a capture process remains after service stop")
    status, camera_output, _error = _run(client, "fuser -v /dev/video* 2>/dev/null || true")
    if status or camera_output.strip():
        raise RuntimeError("refusing restart: a process still owns a camera after service stop")
    status, _output, error = _run(client, "sudo -n systemctl start parr-capture.service")
    if status:
        detail = error.strip() or "command failed"
        raise RuntimeError(f"could not start parr-capture.service: {detail}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--env", type=Path, default=Path(".env"), help="local env file (default: .env)"
    )
    parser.add_argument(
        "--restart", action="store_true", help="restart the installed headless systemd service"
    )
    args = parser.parse_args(argv)
    config = deployment_config(parse_env_file(args.env))
    client = open_ssh_client(config)
    try:
        inspection = inspect_target(client, config)
        for label, output in inspection.items():
            print(f"{label}: {output or 'none'}")
        if args.restart:
            restart_headless_service(client, inspection)
            print("headless parr-capture service restarted")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
