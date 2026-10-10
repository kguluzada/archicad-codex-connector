# Windows installation and diagnosis

## Host preparation

Use a licensed, running Archicad on the same Windows machine as this Python server. Windows 10/11, Archicad 25–30, and Python 3.12–3.14 are the intended target; this repository was automated-tested on macOS with Python 3.12.13 and 3.14.0, not on native Windows. Save a disposable `.pln` project before writes. Keep the target active and close blocking modal dialogs.

The pinned [Tapir 1.7.0 release](https://github.com/ENZYME-APD/tapir-archicad-automation/releases/tag/1.7.0), published 2026-10-04, has the following Windows assets, verified through the release API:

| Archicad | Matching asset |
|---|---|
| 25 | `TapirAddOn_AC25_Win.apx` |
| 26 | `TapirAddOn_AC26_Win.apx` |
| 27 | `TapirAddOn_AC27_Win.apx` |
| 28 | `TapirAddOn_AC28_Win.apx` |
| 29 | `TapirAddOn_AC29_Win.apx` |
| 30 | `TapirAddOn_AC30_Win.apx` |

Download the file for your installed major version. In Archicad: Options → Add-On Manager → Edit List of Available Add-Ons → Add → select the `.apx` → OK. Restart and check it is loaded. Release assets establish distribution coverage; they do not prove this connector has passed a native load or edit test on each major version. The floating installer/latest assets may change; this release uses a manual pinned asset for reproducibility.

## Python installation

Copy the entire checkout to a local path, for example `C:\tools\archicad-connector`. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) and then run:

```powershell
cd C:\tools\archicad-connector
.\scripts\setup.ps1 -PythonVersion 3.12
.\.venv\Scripts\archicad-connector.exe --version
.\.venv\Scripts\archicad-connector.exe diagnose
.\.venv\Scripts\archicad-connector.exe diagnose --port 19723
```

The script checks exit codes, uses the supplied lockfile, and does not alter execution policy or install native add-ons. If local PowerShell policy prevents scripts, run `uv sync --frozen --no-dev --python 3.12` directly. A plain pip installation is also supported, as documented in README; exact direct versions are declared, while the uv lock also fixes transitive versions and platform markers including Windows `pywin32`.

A healthy diagnostic reports a reachable product version/build/language, installed `tapir_version="1.7.0"`, saved project fields and an observed `project_token`. Without `--port`, diagnostics reports all reachable instances and never selects one. Exit 1 means unavailable/failed. An explicit host without Tapir can be reachable while lacking mutation prerequisites; inspect warnings and compatibility rather than just exit status.

The default port range is Graphisoft's 19723–19743. Restrict it with `--ports 19723,19725` or `ARCHICAD_PORTS`. Arguments take precedence over environment defaults. Custom ports are allowed explicitly (useful in tests); no hostname argument exists. `--timeout 30` / `ARCHICAD_TIMEOUT` controls each HTTP attempt; discovery uses short probes. No request retries are enabled.

## Codex registration

Use the TOML file at `examples/codex-config.toml`; replace its absolute executable path. The [official MCP guide](https://learn.chatgpt.com/docs/extend/mcp) documents `mcp_servers.<name>`, stdio `command`, `args`, optional `env` and timeouts. This example keeps the connector on the local Windows execution host. Do not launch it in a Linux/WSL/cloud environment expecting it to control a different machine's desktop.

```powershell
codex mcp add archicad -- C:\tools\archicad-connector\.venv\Scripts\archicad-connector.exe --ports 19723-19743 --timeout 30 serve
codex mcp list
```

Reload Codex and confirm 15 tools are listed. Run discovery/connection/project inspection before a write. For any other MCP client, use the same command/arguments in its local stdio configuration. No OpenAI API key is required by this connector.

## Troubleshooting

| Result | Next action |
|---|---|
| No reachable instances | Start Archicad; inspect JSON port range, local firewall and modal dialogs; retry the read-only diagnostic. |
| Missing Tapir | Load matching 1.7.0 `.apx`, restart and check Add-On Manager. Official reads may still work. |
| Unsupported version/command | Compare exact host and Tapir version; retrieve schema with runtime support check. Do not force a newer schema into an older host. |
| Untitled/changed project | Save a test `.pln`; reinspect the target and use its returned token. |
| Locked/read-only/Teamwork error | Inspect native error code; reserve the element and verify access rights in Archicad. The connector does not reserve automatically. |
| Timeout/outcome unknown | Inspect native GUIDs/model/history before acknowledging the hold. A request can have completed after the timeout. |
| No MCP tools | Verify absolute executable path, run `--version`, inspect stderr, reload client. `diagnose` is not the MCP server command. |

Do not expose Archicad's unauthenticated local JSON port through port forwarding. The connector disables proxy inheritance and restricts addresses to 127.0.0.1. Keep an independent project backup before live acceptance edits.
