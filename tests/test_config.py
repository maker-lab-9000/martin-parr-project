import subprocess
import sys
import types
from pathlib import Path

from firmware.sticks3.scripts.generate_config import (
    firmware_defines,
    parse_env_file,
    platformio_defines,
    platformio_env_file,
)


def test_platformio_quotes_each_setting_with_its_macro_encoder(tmp_path, monkeypatch):
    from firmware.sticks3.scripts import generate_config

    env_file = tmp_path / ".env"
    env_file.write_text(
        'PI_HOST=192.0.2.1\nWIFI_SSID=studio wifi\n'
        'WIFI_PASSWORD=a\\b"c\nPARR_REMOTE_TOKEN=test-token\n'
    )

    class BuildEnv:
        def __init__(self):
            self.encoded = []
            self.defines = None

        def StringifyMacro(self, value):
            self.encoded.append(value)
            return ("encoded", value)

        def Append(self, **kwargs):
            self.defines = kwargs["CPPDEFINES"]

    build_env = BuildEnv()
    scons = types.ModuleType("SCons.Script")
    scons.Import = lambda name: None
    monkeypatch.setitem(sys.modules, "SCons.Script", scons)
    monkeypatch.setattr(generate_config, "env", build_env, raising=False)
    generate_config.configure_platformio(env_file)

    assert build_env.encoded == [
        "studio wifi", 'a\\\\b"c', "http://192.0.2.1:8765", "test-token"
    ]
    assert all(value[0] == "encoded" for _, value in build_env.defines)


def test_parse_env_file_treats_shell_syntax_as_plain_data(tmp_path):
    marker = tmp_path / "must-not-exist"
    env_file = tmp_path / ".env"
    env_file.write_text(
        "PI_HOST=192.168.178.56\n"
        "PI_SSH_PASSWORD=$(touch " + str(marker) + ")\n"
        "WIFI_SSID='studio wifi'\n"
        "WIFI_PASSWORD=literal#password\n"
        "PARR_REMOTE_TOKEN=token-value\n"
    )

    values = parse_env_file(env_file)

    assert values["PI_SSH_PASSWORD"] == f"$(touch {marker})"
    assert values["WIFI_SSID"] == "studio wifi"
    assert not marker.exists()


def test_firmware_defines_include_only_device_credentials_and_api_values():
    defines = dict(
        firmware_defines(
            {
                "PI_HOST": "192.168.178.56",
                "PI_SSH_PASSWORD": "ssh-password-must-not-reach-device",
                "WIFI_SSID": "studio-wifi",
                "WIFI_PASSWORD": "wifi-password",
                "PARR_REMOTE_TOKEN": "remote-token",
            }
        )
    )

    assert defines == {
        "STICKS3_WIFI_SSID": "studio-wifi",
        "STICKS3_WIFI_PASSWORD": "wifi-password",
        "STICKS3_API_BASE": "http://192.168.178.56:8765",
        "STICKS3_API_TOKEN": "remote-token",
    }
    assert "ssh-password-must-not-reach-device" not in defines.values()


def test_platformio_uses_safe_empty_defaults_when_local_env_is_absent(tmp_path):
    assert platformio_defines(tmp_path / ".env") == []


def test_platformio_derives_the_repo_root_env_file_from_its_project_directory(tmp_path):
    project_dir = tmp_path / "repo" / "firmware" / "sticks3"

    assert platformio_env_file(project_dir) == tmp_path / "repo" / ".env"


def test_gitignore_excludes_local_secrets_and_firmware_build_outputs():
    repo_root = Path(__file__).resolve().parents[1]
    paths = [
        ".env",
        ".env.local",
        "firmware/sticks3/.pio/build/sticks3/firmware.bin",
        "firmware/sticks3/include/generated_config.h",
    ]
    ignored = [
        subprocess.run(["git", "check-ignore", "-q", path], cwd=repo_root)
        for path in paths
    ]
    kept_example = subprocess.run(
        ["git", "check-ignore", "-q", ".env.example"], cwd=repo_root
    )

    assert all(result.returncode == 0 for result in ignored)
    assert kept_example.returncode == 1
