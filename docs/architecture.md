# Architecture and execution contract

`MCP stdio client → Python connector → http://127.0.0.1:<explicit port>/ → Archicad JSON → Tapir/native operations`.

The official MCP Python SDK 2.3.0 provides the server/client protocol. The local stdio initialization path negotiates **2025-11-25**; the current SDK also contains the 2026-07-28 revision's per-request protocol. This connector's tested interface is stdio with initialize/tools/list/tools/call. No HTTP MCP endpoint or remote auth service is exposed.

## Boundaries

- `transport.py`: loopback HTTP, official and Tapir envelopes, layered errors, no retries, no proxy inheritance or redirects.
- `catalogue.py` + `data/tapir.json`: reviewed command allowlist, effects, exact native Tapir input schemas, shared refs, and independently authored official input contracts. Native output data is retained; output schema differences become warnings, since Tapir deliberately does not enforce its documented success-only output schema.
- `service.py`: explicit instance sessions, project observation, command availability/version checks, per-instance serialization and in-process operation history.
- `server.py`: 15 MCP tools, strict typed geometry tools, progressive catalogue/schema tools, shared guarded dispatch. No unrestricted forwarding or code evaluation.
- `cli.py`: stdio startup and separate read-only diagnostic JSON output; logging goes to stderr and contains command/operation/port metadata, never whole model payloads.

No C++ add-on is needed for this release's capabilities. Tapir already schedules its `CommandBase` commands on Archicad's main thread. The connector never calls the C++ SDK from an HTTP or Python worker. A native extension would be justified by an atomic native session-identity/project precondition capability, not by recreating existing wall/slab commands.

## Targeting and project identity

`discover_instances` probes configured ports (default Graphisoft range 19723–19743) with an actual `API.GetProductInfo` request rather than trusting an open socket. `connect_instance` requires a port and returns a process-local opaque `instance_id`. Every workflow and dispatcher request uses it. No tool chooses the first instance or falls back to another instance on failure.

Tapir 1.7.0 `GetProjectInfo` returns `isUntitled`, `isTeamwork` and, for saved projects, name/path/location. The inspected code exposes **no native project or open-session GUID**. The connector hashes these observed fields, product version/build/language and instance ID to produce `project_token`. The token is not a guaranteed session identity. Untitled projects and saved projects without a path cannot be mutation targets.

A mutation must include the exact token from an observation. Inside the per-instance lock it validates compatibility, command availability, semantic preconditions and observed project information. It then reads `GetProjectInfo` again immediately before the command dispatch, and rejects a changed observation or mismatched token.

**Limit:** The final check and mutation are separate JSON API calls. A UI/client project switch between them is possible, as is a restart/reopen or replacement of a file with the same observed path and metadata. The connector cannot enforce a native precondition atomically. Keep the target saved project active; use one connector process per host instance and avoid other automation during edits. The lock serializes this process's requests only, not other clients or the user interface.

## Arguments and units

Native schemas retain union branches, refs and optional fields. `null` is never removed or turned into an omitted field. `userUndefined` properties omit `value`; empty string/list and explicit undefined remain different. Strict typed geometry rejects coercible strings, null coordinates and non-finite numbers. The validated dispatcher supports the native allowlist's richer options without flattening their schemas.

Graphisoft JSON uses SI metres/m²/m³/radians regardless of UI units. Coordinates are in Archicad's project frame. No UCS, survey/geolocation transform or unit conversion is assumed.

The inspected wall implementation interprets `zCoordinate` as story-relative bottom offset when `floorIndex` is present, otherwise as absolute project Z. Slab `level` is absolute project Z even with an explicit `floorIndex`: `ResolveFloorIndexAndOffset` subtracts the selected story elevation. Typed workflows require explicit floor indices; default/native settings affect other omitted attributes. Query supported native story indices and attributes before creation.

## Lifecycle and recovery

Dispatch creates an operation ID before acquiring the instance lock: queued → running → succeeded / partial_failure / failed / outcome_unknown. Read/write failures carry native details. Per-item failures are returned with JSON paths and raw data so successful GUIDs are not lost; `partial_failure` means one or more item errors, potentially all items, and is an MCP tool error requiring inspection.

An HTTP connection failure before connection is established is a known transport failure. An incomplete response, write/read timeout, non-200 response or malformed envelope after a mutation request can be an unknown outcome. No write is retried. Further writes in the same process are held until the model has been checked and `acknowledge_unknown_outcome` explicitly names that operation with `model_inspected=true`. This clears a hold only; it does not establish whether a change succeeded or trigger a retry.

Cancellation/disconnection of the client's wait does not deliberately cancel the native operation: dispatched work stays in a retained task and continues recording its outcome while the server process lives. The connector has no native cancellation command or promise. Process termination, host crashes and other clients remain outside its control.

The journal retains up to 100 completed operation metadata entries; queued/running/unknown entries are kept. It does not store model payloads or persist across restart. Restart loses both journal and mutation hold; inspect before resuming after a crash. There is no idempotency/exactly-once guarantee, automatic rollback or dry-run mode.

## Batch and undo behavior

Tapir's creation base wraps a batch in `ACAPI_CallUndoableCommand` but continues after per-item errors and returns `NoError` from the callback. Successful items may remain when others fail. Its inspected source also ignores the outer undo-command return value. The connector reports partial native results and does not infer atomicity or fabricate rollback. Source suggests a native Undo entry for creation; actual undo/redo and outer-command failures must be tested live. Official property updates similarly return per-item execution results and have no connector rollback.

## Adapter scope

The catalogue and transport boundary can accommodate another Archicad backend later. There is no shared Revit/Rhino/Blender/AutoCAD platform, geometry conversion subsystem or event broker here. Dependencies and sources are pinned; extension means adding a reviewed command contract, effect classification, capability checks and tests together.
