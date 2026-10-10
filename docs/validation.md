# Validation record — 2026-10-10

## Automated acceptance

| Check | Result | Scope |
|---|---|---|
| Python 3.12.13 | **44 tests passed** | macOS; pinned dependencies; actual localhost mock HTTP service and MCP stdio subprocess |
| Python 3.14.0 | **44 tests passed** | macOS; connector installed from built wheel rather than source-path injection; full suite and actual console executable |
| Ruff lint | Passed | Connector, tests and vendoring script |
| Ruff formatting | Passed | All 13 Python files |
| Wheel and source build | Passed | Isolated PEP 517 build with hatchling 1.29.0; wheel built from source archive |
| Artifact contents | Passed | Wheel has schema data, Tapir MIT notice, package modules and console entrypoint; source archive has lockfile, tests, Windows setup and live checklist |
| Windows config example | Passed TOML and argument checks | Official documentation checked for namespace, stdio fields and timeouts; no real Windows Codex client launched |
| CLI | Passed | Version/help/error paths, JSON diagnostic against HTTP mock, entrypoint metadata and package resources |

Tests cover exact official/Tapir envelopes, nested schema constraints, missing/null/empty/undefined properties, explicit multiple-instance targeting, malformed and nonfinite host responses, structured native errors, locked/Teamwork-shaped failures, native partial results, project switching immediately before dispatch, untitled-project refusal, capability/version checks, serialized mutations, cancellation of a waiting caller, no automatic write retries, unknown-outcome holds/acknowledgement, archive overwrite refusal, MCP initialization/tool discovery/typed calls, and packaging/configuration.

The complete stdio mock workflow connects, inspects the project, creates wall and slab records, queries and reads their returned GUIDs, updates a typed property and reads it back, then checks undefined/invalid/partial cases. These are **mock native records**, not proof of actual Archicad native objects, placement or editing.

The tested stdio initialization negotiates MCP **2025-11-25** using the official SDK 2.3.0. The latest 2026-07-28 specification uses a distinct modern protocol path; no claim of a 2026-07-28 initialize handshake is made.

## Local host check

`archicad-connector diagnose` on this macOS execution host probed all **21 ports (19723–19743)** and returned `unavailable` with **0 reachable Archicad instances**. No native mutation was attempted. No installed Archicad application was found in the inspected `/Applications` listing. This is evidence about this machine at check time, not about the user's Windows installation.

A local development-environment issue with cache-hardlinked files/hidden editable `.pth` metadata was isolated while testing; the successful Python environments used copied dependencies and the artifact suite used a normal wheel installation. No source work was left dependent on `PYTHONPATH` injection. If macOS Python ignores a hidden editable `.pth`, use a normal wheel install or a copied environment outside a directory whose metadata is managed by another application. This is distinct from Windows acceptance.

## Not executed

- Windows PowerShell execution, native `.apx` installation/load, licensed Archicad commands or actual Codex Windows UI registration.
- Native Wall/Slab element verification, units/story placement, property editability, Undo/Redo, real Teamwork ownership/access failures, localized paths, co-installed add-ins or real modal/busy-host timeouts.
- Native same-document identity/atomic project precondition, rollback/cancellation/dry-run/exactly-once behavior or large-model benchmarks.
- Python 3.13 and individual third-party MCP clients.

Run [the Windows live checklist](live-validation.md) before classifying any specific Archicad/Windows combination as live validated. [Compatibility](compatibility.md) distinguishes asset/source support, automated mock evidence and missing live evidence.
