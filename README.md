# Archicad connector for Codex and MCP

A local Python MCP server using Graphisoft's HTTP JSON API and Tapir 1.7.0. Source and automated tests are included. **Native Windows/Archicad execution has not yet been validated.** The compatibility range comes from inspected source and release assets, not a live certification.

See [test results](docs/validation.md), [Windows setup](docs/windows.md), [capabilities](docs/capabilities.md), [architecture](docs/architecture.md), [source and license ledger](docs/sources.md), [compatibility](docs/compatibility.md), and [live acceptance checklist](docs/live-validation.md).

Sign in at [download.kaan.win](https://download.kaan.win) to choose the complete Windows setup ZIP or individual files. The [project pages](https://archicad.kaan.win) include installation and validation details. Source, tests and public releases are hosted at [kguluzada/archicad-codex-connector](https://github.com/kguluzada/archicad-codex-connector). The ZIP includes source, documentation, setup scripts and a wheel; Python, Archicad and Tapir are installed separately.

## Quick start on Windows

Run on the same Windows machine as your running, licensed Archicad installation. Python 3.12–3.14 is required; Automated tests passed on Python 3.12.13 and 3.14.0.

```powershell
# From the connector checkout; no activation or execution-policy changes needed
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\archicad-connector.exe diagnose
.\.venv\Scripts\archicad-connector.exe diagnose --port 19723
```

For a fully locked installation use `scripts/setup.ps1` with `uv` installed (it runs `uv sync --frozen --no-dev`). Install the matching AC25–30 Windows `.apx` from [Tapir 1.7.0](https://github.com/ENZYME-APD/tapir-archicad-automation/releases/tag/1.7.0) through Options → Add-On Manager, then restart Archicad. Never load an asset for a different Archicad major version. See Windows setup for exact asset names.

## Connect Codex

Append this example to `%USERPROFILE%\.codex\config.toml`, substituting your actual checkout path. Absolute executable paths avoid working-directory and PATH dependence. This follows the [official Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp). TOML structure and stdio handshake are automated-tested; a Windows Codex GUI connection remains a live acceptance step.

```toml
[mcp_servers.archicad]
command = 'C:\tools\archicad-connector\.venv\Scripts\archicad-connector.exe'
args = ['--ports', '19723-19743', '--timeout', '30', 'serve']
startup_timeout_sec = 30
tool_timeout_sec = 120
```

Alternatively, with Codex CLI installed:

```powershell
codex mcp add archicad -- C:\tools\archicad-connector\.venv\Scripts\archicad-connector.exe --ports 19723-19743 serve
codex mcp list
```

Restart/reload your MCP client. Other local MCP clients can launch the same executable and arguments using their stdio configuration. `serve` reserves stdout for protocol messages; diagnostics is a separate subcommand.

## First use

1. Ask the client to run `discover_instances`, then `connect_instance` with an explicit returned port. Multiple instances never cause automatic selection.
2. Inspect the returned version, saved project information and `project_token`. Use `inspect_project` to refresh them. Keep this project active throughout a write.
3. Run `inspect_selection`, `query_elements` with `element_type="Wall"`, and `read_elements` for explicit returned native GUIDs. Use `list_attributes` with `attribute_type="Layer"`.
4. Use `search_commands` then `get_command_schema` for `tapir.GetStories` and `official.GetPropertyIds`. Run them through `execute_command`.
5. Create a wall/slab with the typed tools and **explicit** `instance_id` and `project_token`. Coordinates and lengths are metres; angles are radians. Use the story indices returned by Archicad. Wall `zCoordinate` is a story-relative offset when `floorIndex` is supplied. See capabilities for slab level semantics.
6. Resolve an existing writable property, inspect `official.GetDetailsOfProperties`, use `update_property`, and read the value back. A normal value looks like `{"type":"string","status":"normal","value":"MCP validation"}`. An undefined value uses `{"type":"string","status":"userUndefined"}` with the `value` key **absent**.
7. Inspect native objects and results. Batch results can include errors alongside successful GUIDs; no all-or-nothing guarantee exists. Never retry a timed-out write blindly.

See `examples/wall.json` and `examples/slab.json` for geometry payloads; insert your real target fields into the typed tool calls. Dispatcher schemas preserve missing/null/empty distinctions and unions; unsupported nulls are rejected rather than silently deleted.

## Development and verification

```sh
uv sync --frozen
uv run --frozen pytest -q
uv run --frozen ruff check src tests scripts
uv run --frozen python -m build
```

The tests start a real local mock HTTP service, verify native envelopes and failure behavior, and exercise MCP over stdio using the official SDK client. No commercial application or remote server is needed for them. Live acceptance is separately documented.

## Limits

The reviewed catalogue has 30 native commands and 15 MCP tools. No arbitrary command passthrough, Python/GDL execution, new C++ add-on, remote network endpoint or multi-application broker is added. Official reads can work without Tapir; mutations need Tapir project checks. Known Tapir schema version mismatches fail closed.

Project targeting uses an observed fingerprint, **not** a native session GUID. Writes to untitled projects are refused. A close/reopen of the same saved path or a UI switch between the final project check and native execution is not detectable with this backend. Only one connector process should control a given instance. Do not expose Archicad's unauthenticated JSON API to a network.

An uncertain write holds further mutations in this process until inspection and explicit acknowledgement. The bounded operation journal is in memory: restart loses the hold and history. There is no automatic write retry, rollback, exactly-once execution, verified cancellation or dry-run. See the architecture document for recovery and native execution details.
