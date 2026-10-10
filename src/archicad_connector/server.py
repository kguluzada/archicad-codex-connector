"""Compact MCP surface; large native command schemas are fetched on demand."""

import json
from contextlib import asynccontextmanager
from functools import wraps
from typing import Annotated, Literal

from mcp.server.mcpserver import MCPServer
from mcp_types import CallToolResult, TextContent, ToolAnnotations
from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from . import __version__
from .errors import ConnectorError
from .service import Connector


class Coordinate(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    x: float
    y: float


class Wall(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    begCoordinate: Coordinate
    endCoordinate: Coordinate
    height: Annotated[float, Field(gt=0)]
    thickness: Annotated[float, Field(gt=0)]
    floorIndex: int
    zCoordinate: float = 0.0


class Slab(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    level: float
    polygonCoordinates: Annotated[list[Coordinate], Field(min_length=3)]
    floorIndex: int
    thickness: Annotated[float, Field(gt=0)]


def tool_result(data):
    failed = data.get("status") in {"failed", "partial_failure", "outcome_unknown"}
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(data, ensure_ascii=False))],
        structured_content=data,
        is_error=failed,
    )


def guarded(function):
    @wraps(function)
    async def invoke(*args, **kwargs):
        try:
            return tool_result(await function(*args, **kwargs))
        except ConnectorError as error:
            return tool_result({"status": "failed", "errors": [error.as_dict()]})

    return invoke


def create_server(connector=None):
    service = connector or Connector()

    @asynccontextmanager
    async def lifespan(_):
        try:
            yield service
        finally:
            await service.close()

    server = MCPServer(
        "archicad-connector",
        version=__version__,
        lifespan=lifespan,
        log_level="WARNING",
        instructions="Discover and connect to an explicit port. Retrieve native schemas on demand. "
        "All units are SI, geometry in Archicad project coordinates. Writes require instance_id "
        "and the current observed project_token. Keep that saved project active during writes. "
        "Unknown outcomes must be inspected before another write.",
    )
    read = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
    write = ToolAnnotations(
        read_only_hint=False, destructive_hint=True, idempotent_hint=False, open_world_hint=False
    )

    @server.tool(annotations=read)
    @guarded
    async def discover_instances() -> CallToolResult:
        """Probe configured local ports; never select an instance implicitly."""
        return await service.discover()

    @server.tool(annotations=read)
    @guarded
    async def connect_instance(port: StrictInt) -> CallToolResult:
        """Select a discovered port; return host/Tapir versions, project and target token."""
        return await service.connect(port)

    @server.tool(annotations=read)
    @guarded
    async def inspect_project(instance_id: StrictStr) -> CallToolResult:
        """Refresh project information, observed fingerprint, versions and connection state."""
        return await service.status(instance_id)

    @server.tool(annotations=read)
    @guarded
    async def search_commands(query: str = "", offset: int = 0, limit: int = 20) -> CallToolResult:
        """Search the reviewed catalogue; compact results include backend and effect."""
        return service.catalogue.search(query, offset, limit)

    @server.tool(annotations=read)
    @guarded
    async def get_command_schema(command: StrictStr, instance_id: StrictStr | None = None) -> CallToolResult:
        """Fetch a native input schema (including refs/unions), limitations and optional runtime support."""
        return await service.command_schema(command, instance_id)

    @server.tool(annotations=read)
    @guarded
    async def inspect_selection(instance_id: StrictStr) -> CallToolResult:
        """Return native GUIDs of selected supported elements in the current plan."""
        return await service.dispatch(instance_id, "official.GetSelectedElements", {})

    @server.tool(annotations=read)
    @guarded
    async def query_elements(
        instance_id: StrictStr, element_type: StrictStr, filters: list[StrictStr] | None = None
    ) -> CallToolResult:
        """Query native elements; filters use Tapir's ElementFilter enum, fetched via get_command_schema."""
        arguments = {"elementType": element_type}
        if filters is not None:
            arguments["filters"] = filters
        return await service.dispatch(instance_id, "tapir.GetElementsByType", arguments)

    @server.tool(annotations=read)
    @guarded
    async def read_elements(
        instance_id: StrictStr,
        element_ids: list[StrictStr],
        detail: Literal["geometry", "properties", "classifications"] = "geometry",
        property_ids: list[StrictStr] | None = None,
    ) -> CallToolResult:
        """Read geometry, property values (explicit property_ids), or classification assignments."""
        elements = [{"elementId": {"guid": guid}} for guid in element_ids]
        if detail == "properties":
            if property_ids is None:
                raise ConnectorError(
                    "invalid_arguments",
                    "Provide property_ids; resolve them with official.GetPropertyIds first.",
                )
            return await service.dispatch(
                instance_id,
                "official.GetPropertyValuesOfElements",
                {"elements": elements, "properties": [{"propertyId": {"guid": p}} for p in property_ids]},
            )
        command = (
            "tapir.GetDetailsOfElements" if detail == "geometry" else "tapir.GetClassificationsOfElements"
        )
        return await service.dispatch(instance_id, command, {"elements": elements})

    @server.tool(annotations=read)
    @guarded
    async def list_attributes(instance_id: StrictStr, attribute_type: StrictStr) -> CallToolResult:
        """List available native attributes such as Layer or BuildingMaterial."""
        return await service.dispatch(
            instance_id, "tapir.GetAttributesByType", {"attributeType": attribute_type}
        )

    @server.tool(annotations=write)
    @guarded
    async def create_walls(
        instance_id: StrictStr, project_token: StrictStr, walls: Annotated[list[Wall], Field(min_length=1)]
    ) -> CallToolResult:
        """Create native straight walls. SI metres; XY project coords.
        zCoordinate is an offset relative to floorIndex.

        Retrieve GetStories first. More native options are available through the validated dispatcher.
        """
        return await service.dispatch(
            instance_id,
            "tapir.CreateWalls",
            {"wallsData": [w.model_dump(exclude_unset=True) for w in walls]},
            project_token,
        )

    @server.tool(annotations=write)
    @guarded
    async def create_slabs(
        instance_id: StrictStr, project_token: StrictStr, slabs: Annotated[list[Slab], Field(min_length=1)]
    ) -> CallToolResult:
        """Create native slabs. SI metres; XY project coords; level is absolute project Z.

        Polygon closure/holes/arcs follow the native schema through the dispatcher.
        """
        return await service.dispatch(
            instance_id,
            "tapir.CreateSlabs",
            {"slabsData": [s.model_dump(exclude_unset=True) for s in slabs]},
            project_token,
        )

    @server.tool(annotations=write)
    @guarded
    async def update_property(
        instance_id: StrictStr,
        project_token: StrictStr,
        element_ids: list[StrictStr],
        property_id: StrictStr,
        property_value: dict,
    ) -> CallToolResult:
        """Set one existing, editable property on explicit GUIDs. Native value has type/status/value;
        userUndefined deliberately omits value. Retrieve the schema for exact enum/list forms.
        """
        values = [
            {"elementId": {"guid": e}, "propertyId": {"guid": property_id}, "propertyValue": property_value}
            for e in element_ids
        ]
        return await service.dispatch(
            instance_id,
            "official.SetPropertyValuesOfElements",
            {"elementPropertyValues": values},
            project_token,
        )

    @server.tool(annotations=write)
    @guarded
    async def execute_command(
        instance_id: StrictStr, command: StrictStr, arguments: dict, project_token: StrictStr | None = None
    ) -> CallToolResult:
        """Dispatch ONLY reviewed commands after native schema validation. Fetch schema before use.
        Conservatively annotated as modifying: actual effect is in command metadata. No code execution.
        """
        return await service.dispatch(instance_id, command, arguments, project_token)

    @server.tool(annotations=read)
    @guarded
    async def get_operation_status(operation_id: StrictStr) -> CallToolResult:
        """Read retained in-process state; no persistence or exactly-once guarantee."""
        return service.operation_status(operation_id)

    @server.tool(annotations=write)
    @guarded
    async def acknowledge_unknown_outcome(
        instance_id: StrictStr, operation_id: StrictStr, model_inspected: bool
    ) -> CallToolResult:
        """After checking the native model, explicitly clear a write hold. Does not retry or prove outcome."""
        return await service.acknowledge_unknown(instance_id, operation_id, model_inspected)

    return server
