import pytest

from scripts.deploy_remote import (
    DeploymentConfig,
    build_capture_command,
    open_ssh_client,
    restart_headless_service,
)


class FakeClient:
    def __init__(self):
        self.calls = []

    def load_system_host_keys(self):
        self.calls.append(("load_system_host_keys",))

    def set_missing_host_key_policy(self, policy):
        self.calls.append(("set_missing_host_key_policy", policy))

    def connect(self, **kwargs):
        self.calls.append(("connect", kwargs))


class FakeParamiko:
    class RejectPolicy:
        pass

    class SSHClient(FakeClient):
        pass


class FakeStream:
    def __init__(self, status=0, output=""):
        self.channel = self
        self.status = status
        self.output = output.encode()

    def recv_exit_status(self):
        return self.status

    def read(self):
        return self.output


class RestartClient:
    def __init__(self):
        self.commands = []

    def exec_command(self, command):
        self.commands.append(command)
        return None, FakeStream(), FakeStream()


def test_capture_command_uses_verified_artifact_directory_and_never_includes_token():
    config = DeploymentConfig(
        host="192.168.178.56",
        user="george",
        project_dir="/home/george/repos/martin-parr-project",
        ssh_password="ssh-secret",
        artifact_dir="/home/george/parr artifacts/personal-v1",
        remote_token="remote-secret",
    )

    command = build_capture_command(config, show_captures=True)

    assert command == (
        "/home/george/repos/martin-parr-project/.venv/bin/parr-capture --no-preview "
        "--show-captures --remote-listen 192.168.178.56:8765 --artifacts "
        "'/home/george/parr artifacts/personal-v1'"
    )
    assert "remote-secret" not in command
    assert "ssh-secret" not in command


def test_open_ssh_client_rejects_unknown_host_keys_before_password_connection():
    config = DeploymentConfig(
        host="192.168.178.56",
        user="george",
        project_dir="/home/george/repos/martin-parr-project",
        ssh_password="ssh-secret",
        artifact_dir="/home/george/artifacts/personal-v1",
        remote_token="remote-secret",
    )

    client = open_ssh_client(config, paramiko_module=FakeParamiko)

    assert client.calls[0] == ("load_system_host_keys",)
    assert isinstance(client.calls[1][1], FakeParamiko.RejectPolicy)
    assert client.calls[2] == (
        "connect",
        {
            "hostname": "192.168.178.56",
            "username": "george",
            "password": "ssh-secret",
            "look_for_keys": False,
            "allow_agent": False,
            "timeout": 15,
        },
    )


def test_restart_stops_the_current_service_before_rechecking_its_camera_owner():
    client = RestartClient()

    restart_headless_service(
        client,
        {
            "camera owners": "1234  /home/george/.venv/bin/parr-capture",
            "capture process": "1234 parr-capture",
            "service pid": "1234",
        },
    )

    assert client.commands == [
        "sudo -n systemctl stop parr-capture.service",
        "pgrep -af '[p]arr-capture' || true",
        "fuser -v /dev/video* 2>/dev/null || true",
        "sudo -n systemctl start parr-capture.service",
    ]


def test_restart_refuses_a_foreign_camera_owner_before_stopping_the_service():
    client = RestartClient()

    with pytest.raises(RuntimeError, match="foreign capture or camera owner"):
        restart_headless_service(
            client,
            {
                "camera owners": "4321  /usr/bin/other-camera-app",
                "capture process": "4321 other-camera-app",
                "service pid": "1234",
            },
        )

    assert client.commands == []
