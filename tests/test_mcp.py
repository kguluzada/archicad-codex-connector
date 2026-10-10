import json
import os
import sys
from uuid import uuid4

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def test_stdio_initialization_and_complete_workflow(host, wall, tmp_path):
    stderr_path = tmp_path / "mcp-stderr.log"
    with stderr_path.open("w") as stderr:
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "archicad_connector", "--ports", str(host.port), "serve"],
            env={**os.environ},
        )
        async with stdio_client(parameters, errlog=stderr) as (read, write):
            async with ClientSession(read, write, read_timeout_seconds=30) as session:
                initialized = await session.initialize()
                assert initialized.server_info.name == "archicad-connector"
                assert initialized.protocol_version == "2025-11-25"
                tools = (await session.list_tools()).tools
                names = {tool.name for tool in tools}
                assert len(names) == 15
                assert "CreateWalls" not in names  # Native schemas only retrieved on demand.
                assert "execute_command" in names
                create = next(t for t in tools if t.name == "create_walls")
                assert create.annotations.destructive_hint
                assert "minItems" in json.dumps(create.input_schema)

                async def call(name, arguments):
                    result = await session.call_tool(name, arguments)
                    assert not result.is_error, result.content
                    data = result.structured_content
                    assert data == json.loads(result.content[0].text)
                    return data

                discovered = await call("discover_instances", {})
                assert discovered["instances"][0]["port"] == host.port
                target = await call("connect_instance", {"port": host.port})
                fields = {"instance_id": target["instance_id"], "project_token": target["project_token"]}
                schema = await call("get_command_schema", {"command": "tapir.CreateWalls"})
                assert schema["input_schema"]["properties"]["wallsData"]["items"]["required"]
                wall_result = await call("create_walls", {**fields, "walls": [wall]})
                wall_id = wall_result["data"]["elements"][0]["elementId"]["guid"]
                slab = {
                    "level": 0.0,
                    "thickness": 0.25,
                    "floorIndex": 0,
                    "polygonCoordinates": [
                        {"x": 0.0, "y": 0.0},
                        {"x": 5.0, "y": 0.0},
                        {"x": 5.0, "y": 4.0},
                        {"x": 0.0, "y": 4.0},
                    ],
                }
                slab_result = await call("create_slabs", {**fields, "slabs": [slab]})
                slab_id = slab_result["data"]["elements"][0]["elementId"]["guid"]
                assert host.elements[slab_id]["type"] == "Slab"
                query = await call(
                    "query_elements", {"instance_id": target["instance_id"], "element_type": "Wall"}
                )
                assert query["data"]["elements"] == [{"elementId": {"guid": wall_id}}]
                details = await call(
                    "read_elements", {"instance_id": target["instance_id"], "element_ids": [wall_id]}
                )
                assert details["data"]["detailsOfElements"][0]["type"] == "Wall"
                property_id = str(uuid4())
                value = {"type": "string", "status": "normal", "value": ""}
                await call(
                    "update_property",
                    {**fields, "element_ids": [wall_id], "property_id": property_id, "property_value": value},
                )
                values = await call(
                    "read_elements",
                    {
                        "instance_id": target["instance_id"],
                        "element_ids": [wall_id],
                        "detail": "properties",
                        "property_ids": [property_id],
                    },
                )
                assert (
                    values["data"]["propertyValuesForElements"][0]["propertyValues"][0]["propertyValue"]
                    == value
                )
                undefined = {"type": "string", "status": "userUndefined"}
                await call(
                    "update_property",
                    {
                        **fields,
                        "element_ids": [wall_id],
                        "property_id": property_id,
                        "property_value": undefined,
                    },
                )
                assert host.values[(wall_id, property_id)] == undefined
                assert (
                    "value"
                    not in host.requests[-1]["parameters"]["elementPropertyValues"][0]["propertyValue"]
                )
                rejected = await session.call_tool(
                    "execute_command", {**fields, "command": "tapir.QuitArchicad", "arguments": {}}
                )
                assert rejected.is_error
                assert rejected.structured_content["errors"][0]["code"] == "unsupported_command"
                invalid = await session.call_tool(
                    "create_walls", {**fields, "walls": [{**wall, "height": None}]}
                )
                assert invalid.is_error
                host.partial = True
                partial = await session.call_tool("create_walls", {**fields, "walls": [wall, wall]})
                assert partial.is_error
                assert partial.structured_content["status"] == "partial_failure"
    logs = stderr_path.read_text()
    assert "begCoordinate" not in logs and "MCP validation" not in logs
