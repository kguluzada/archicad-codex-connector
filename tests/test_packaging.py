import json
import subprocess
import sys
import tomllib
from importlib.metadata import distribution
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_console_entrypoint_and_bundled_data():
    package = distribution("archicad-codex-connector")
    entry = next(ep for ep in package.entry_points if ep.name == "archicad-connector")
    assert entry.load().__module__ == "archicad_connector.cli"
    from importlib.resources import files

    resource = files("archicad_connector").joinpath("data/tapir.json")
    assert json.loads(resource.read_text())["release"] == "1.7.0"
    assert "MIT License" in files("archicad_connector").joinpath("data/TAPIR_LICENSE.txt").read_text()


def test_cli_and_json_diagnostics(host):
    executable = Path(sys.executable).parent / (
        "archicad-connector.exe" if sys.platform == "win32" else "archicad-connector"
    )
    version = subprocess.run([str(executable), "--version"], capture_output=True, text=True, timeout=30)
    assert version.returncode == 0 and version.stdout.strip() == "0.1.0"
    diagnostic = subprocess.run(
        [str(executable), "--ports", str(host.port), "diagnose", "--port", str(host.port)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert diagnostic.returncode == 0, diagnostic.stderr
    data = json.loads(diagnostic.stdout)
    assert data["target"]["tapir_version"] == "1.7.0"
    bad = subprocess.run(
        [str(executable), "--ports", "bad", "serve"], capture_output=True, text=True, timeout=30
    )
    assert bad.returncode == 2 and not bad.stdout


def test_codex_config_is_valid_toml():
    config = tomllib.loads((ROOT / "examples/codex-config.toml").read_text())
    server = config["mcp_servers"]["archicad"]
    assert server["command"].endswith("archicad-connector.exe")
    assert server["args"][-1] == "serve"
    assert server["tool_timeout_sec"] > 2 * int(server["args"][-2])
