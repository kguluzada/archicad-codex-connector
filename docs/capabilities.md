# Command and capability guide

The 15 MCP tools expose discovery, connection/project status, search/schema lookup, selection/query/detail/attribute reads, native wall/slab creation, property updates, reviewed dispatch, operation status and unknown-outcome acknowledgement. No arbitrary command forwarding or native code execution is exposed.

`search_commands` returns compact descriptions, source backend, effect and minimum command metadata. `get_command_schema` returns the complete native input schema on demand, its referenced definitions, documented Tapir output schema (when available), SI units, compatibility/atomicity/recovery limits and optional runtime availability. The MCP client receives only the compact tool surface at tool discovery, not 30 entire native schemas.

## Reviewed native commands

| Backend | Effect | Commands |
|---|---|---|
| Graphisoft official | Read | `GetProductInfo`, `IsAlive`, `GetAllElements`, `GetSelectedElements`, `GetElementsByType`, `GetAllPropertyNames`, `GetPropertyIds`, `GetDetailsOfProperties`, `GetPropertyValuesOfElements`, `GetAllClassificationSystems`, `GetClassificationsOfElements` |
| Graphisoft official | Model | `SetPropertyValuesOfElements` |
| Tapir | Read | `GetAddOnVersion`, `GetCurrentWindowType`, `GetProjectInfo`, `GetStories`, `GetSelectedElements`, `GetElementsByType`, `GetAllElements`, `FilterElements`, `GetDetailsOfElements`, `GetAllProperties`, `GetClassificationsOfElements`, `GetAttributesByType`, `GetLayers`, `GetBuildingMaterials` |
| Tapir | Model | `CreateWalls`, `CreateSlabs` |
| Tapir | Application state | `ChangeSelectionOfElements` |
| Tapir | Files and application state | `SaveProjectAsArchive` |

Dispatcher names are `official.<name>` or `tapir.<name>`, for example `tapir.CreateWalls`. The host wire namespace is `API.<name>` for official commands and `TapirCommand` through `API.ExecuteAddOnCommand` for Tapir. Unsupported names never reach the host.

## Typed tools

| Tool | Input and behavior |
|---|---|
| `discover_instances` | Actual product probes on configured local ports; all reachable instances reported. |
| `connect_instance` | Explicit port; returns instance ID, version/build/language, Tapir version, observed project token and limitations. |
| `inspect_project` | Explicit instance ID; refreshes the same status without choosing another instance. |
| `inspect_selection` | Official selected elements in the plan; result includes native GUID objects. |
| `query_elements` | Native `element_type` and optional nonempty `filters` from Tapir's enum. Missing filter differs from null/empty native dispatcher arguments. |
| `read_elements` | Explicit GUID strings. `detail="geometry"`, `"classifications"`, or `"properties"` with explicit `property_ids`. |
| `list_attributes` | Native attribute type such as `Layer`, `BuildingMaterial`, `Composite`, `Surface`, `Profile`. |
| `create_walls` | Nonempty strict wall list. Required XY endpoints, positive height/thickness and integer story index. Optional `zCoordinate` is a **relative story offset** with `floorIndex`. |
| `create_slabs` | Nonempty strict slab list. At least three XY vertices, absolute project Z `level`, positive thickness and integer story index. Native creation uses current defaults for omitted settings. |
| `update_property` | Explicit element GUIDs, property GUID and native typed property value. Sets one supported property on those elements, not a guessed selection. |

Typed tools use the same schema validation and project guard as `execute_command`. Fetch the full native schema and use the dispatcher for favorites, curved walls, materials, reference lines, slab holes/arcs or other reviewed options. Passing empty/null data where the native schema forbids it is an error; optional fields are not silently normalized.

## Geometry and project context

The JSON interface uses SI, independently of display preferences. XY is the Archicad project frame, not map/survey/world coordinates from another application. A wall with `floorIndex=1, zCoordinate=0` starts at story 1. A slab with `floorIndex=1, level=0` places its reference plane at **absolute Z=0**, which may be below story 1. Use `GetStories` and consciously supply the desired slab absolute level. The polygon closure/arcs/hole contract follows the pinned native schema and native geometry builder; no independent mesh approximation is returned.

Read details return the native type-specific data. Native defaults/favorites, composites and project attributes affect actual wall/slab geometry; dimensions must be verified inside Archicad. Query scope is the native command's current plan/database semantics, not a universal cross-view search. Bulk reads have no connector pagination/cursor or response-size guarantee in this first version. Narrow query types/filters and detail `fields` via the dispatcher on large models.

## Properties and classifications

Resolve a property through `official.GetPropertyIds` using either `{"type":"BuiltIn","nonLocalizedName":"General_ElementID"}` or a user-defined `[group, name]` localized pair. Inspect `official.GetDetailsOfProperties` for type/editability; built-in or computed properties may be read-only. The official value contract supports scalar/list number/integer/string/boolean and length/area/volume/angle, single/multiple enumeration values, and `userUndefined` with the `value` key absent. `null` is not undefined. Enum values use native displayed/nonlocalized IDs; retrieve the schema before setting them.

`tapir.GetPropertyValuesOfElements` (not included here) uses display strings in its own contract; this connector's typed property read/write workflow deliberately uses the official typed value contract. Native item errors identify unavailable properties, locked elements and Teamwork rights; the connector does not bypass permissions or infer successful updates.

Typed classification reads use Tapir assignments. Official classification reads require explicit `classificationSystemIds`; discover systems with `official.GetAllClassificationSystems`, then dispatch the read command with its exact schema. Attribute queries return native names/indices/GUIDs so native references can be used in subsequent operations.

## File operation

`tapir.SaveProjectAsArchive` writes a `.pla` and makes that archive the open project. The connector requires an explicit saved project token and an **absolute, new** `.pla` destination; it refuses an existing target because the native command overwrites it. Parent permissions, disk space and native archive contents are host concerns and require live validation. The local existence check is not an atomic filesystem reservation; avoid concurrent writers to that destination. After Save As, refresh the project's token.

## Failures

Results preserve native data, per-item error paths, warnings, operation ID and actual lifecycle state. Partial native failures set MCP `isError=true` while keeping successful GUIDs in structured content. A timeout after a write or malformed response can be `outcome_unknown`; further writes are held until explicit acknowledgement after model inspection. No automatic retry, transaction rollback, dry-run, native cancellation or exactly-once claim is made. See architecture and live checklist for limits.
