import asyncio
import copy
from uuid import uuid4

import pytest

from archicad_connector.catalogue import Catalogue
from archicad_connector.cli import parse_ports
from archicad_connector.errors import ConnectorError
from archicad_connector.service import Connector
from archicad_connector.transport import envelope


def test_exact_envelopes():
    assert envelope("official", "GetProductInfo", {}) == {"command": "API.GetProductInfo", "parameters": {}}
    assert envelope("tapir", "CreateWalls", {"wallsData": []}) == {
        "command": "API.ExecuteAddOnCommand",
        "parameters": {
            "addOnCommandId": {"commandNamespace": "TapirCommand", "commandName": "CreateWalls"},
            "addOnCommandParameters": {"wallsData": []},
        },
    }


def test_catalogue_is_allowlist_with_effects_and_exact_refs():
    catalogue = Catalogue()
    assert len(catalogue.commands) == 30
    assert {c["effect"] for c in catalogue.commands.values()} == {"read", "model", "application", "files"}
    schema = catalogue.schema("tapir.CreateSlabs")
    assert schema["properties"]["slabsData"]["items"]["properties"]["polygonCoordinates"]["minItems"] == 3
    assert "Coordinate2D" in schema["definitions"]
    assert catalogue.search("wall")["total"] > 0
    assert len(catalogue.search(limit=1)["commands"]) == 1
    with pytest.raises(ConnectorError, match="outside"):
        catalogue.get("tapir.ExecutePython")


@pytest.mark.parametrize(
    "field,value",
    [
        ("height", None),
        ("height", 0),
        ("height", -1),
        ("height", "3"),
        ("floorIndex", None),
        ("begCoordinate", {"x": 0}),
        ("extra", 1),
    ],
)
def test_invalid_nested_arguments(wall, field, value):
    wall[field] = value
    with pytest.raises(ConnectorError):
        Catalogue().validate("tapir.CreateWalls", {"wallsData": [wall]})


def test_missing_empty_null_unset_are_distinct(wall):
    c = Catalogue()
    c.validate("tapir.CreateWalls", {"wallsData": [wall]})
    wall["favoriteName"] = ""
    c.validate("tapir.CreateWalls", {"wallsData": [wall]})
    wall["favoriteName"] = None
    with pytest.raises(ConnectorError):
        c.validate("tapir.CreateWalls", {"wallsData": [wall]})
    ids = {"elementId": {"guid": str(uuid4())}, "propertyId": {"guid": str(uuid4())}}
    undefined = {"type": "string", "status": "userUndefined"}
    c.validate(
        "official.SetPropertyValuesOfElements",
        {"elementPropertyValues": [{**ids, "propertyValue": undefined}]},
    )
    with pytest.raises(ConnectorError):
        c.validate(
            "official.SetPropertyValuesOfElements",
            {"elementPropertyValues": [{**ids, "propertyValue": {**undefined, "value": None}}]},
        )
    c.validate(
        "official.SetPropertyValuesOfElements",
        {
            "elementPropertyValues": [
                {**ids, "propertyValue": {"type": "string", "status": "normal", "value": ""}}
            ]
        },
    )


async def test_discovery_multiple_and_no_implicit_target(host):
    from conftest import MockArchicad

    other = MockArchicad()
    service = Connector([host.port, other.port])
    try:
        result = await service.discover()
        assert len(result["instances"]) == 2
        assert result["multiple_instances"] and result["selection_required"]
        with pytest.raises(ConnectorError):
            await service.dispatch("", "official.IsAlive", {})
        first, second = await service.connect(host.port), await service.connect(other.port)
        assert first["instance_id"] != second["instance_id"]
        assert first["project_token"] != second["project_token"]
    finally:
        await service.close()
        other.close()


async def test_discovery_rejects_non_archicad_service(host, connector):
    host.version = "not Archicad"
    assert (await connector.discover())["instances"] == []


async def test_exact_live_http_envelopes(host, connector, target, wall):
    result = await connector.dispatch(
        target["instance_id"], "tapir.CreateWalls", {"wallsData": [wall]}, target["project_token"]
    )
    assert result["status"] == "succeeded"
    assert host.requests[-1] == envelope("tapir", "CreateWalls", {"wallsData": [wall]})
    guid = result["data"]["elements"][0]["elementId"]["guid"]
    assert guid in host.elements
    await connector.dispatch(target["instance_id"], "official.GetSelectedElements", {})
    assert host.requests[-1] == envelope("official", "GetSelectedElements", {})


async def test_validation_prevents_http(host, connector, target):
    before = len(host.requests)
    with pytest.raises(ConnectorError):
        await connector.dispatch(
            target["instance_id"], "tapir.CreateWalls", {"wallsData": None}, target["project_token"]
        )
    assert len(host.requests) == before


async def test_explicit_project_required(host, connector, target, wall):
    with pytest.raises(ConnectorError, match="project_token"):
        await connector.dispatch(target["instance_id"], "tapir.CreateWalls", {"wallsData": [wall]})
    assert host.mutations == 0


async def test_final_project_check(host, connector, target, wall):
    host.switch_at = host.project_reads + 2
    result = await connector.dispatch(
        target["instance_id"], "tapir.CreateWalls", {"wallsData": [wall]}, target["project_token"]
    )
    assert result["errors"][0]["code"] == "project_changed"
    assert host.mutations == 0


async def test_untitled_refused(host, connector, wall):
    host.project = {"isUntitled": True, "isTeamwork": False}
    target = await connector.connect(host.port)
    result = await connector.dispatch(
        target["instance_id"], "tapir.CreateWalls", {"wallsData": [wall]}, target["project_token"]
    )
    assert result["errors"][0]["code"] == "unsafe_project_target"
    assert host.mutations == 0


@pytest.mark.parametrize(
    "missing,version,command,code",
    [
        (True, "1.7.0", "CreateWalls", "missing_tapir"),
        (False, "1.5.9", "CreateWalls", "unsupported_version"),
        (False, "1.7.0", "CreateWalls", "unsupported_command"),
    ],
)
async def test_capability_checks(host, connector, target, wall, missing, version, command, code):
    host.missing_tapir = missing
    host.tapir_version = version
    if code == "unsupported_command":
        host.unavailable_commands.add(command)
    result = await connector.dispatch(
        target["instance_id"], "tapir.CreateWalls", {"wallsData": [wall]}, target["project_token"]
    )
    assert result["errors"][0]["code"] == code
    assert host.mutations == 0


async def test_official_read_without_tapir(host, connector):
    host.missing_tapir = True
    target = await connector.connect(host.port)
    assert target["project_token"] is None
    result = await connector.dispatch(target["instance_id"], "official.GetSelectedElements", {})
    assert result["status"] == "succeeded"


async def test_unsupported_archicad_version(host, connector, target):
    host.version = 31
    result = await connector.dispatch(target["instance_id"], "official.GetSelectedElements", {})
    assert result["errors"][0]["code"] == "unsupported_version"


async def test_locked_and_teamwork_errors(host, connector, target, wall):
    host.locked = True
    result = await connector.dispatch(
        target["instance_id"], "tapir.CreateWalls", {"wallsData": [wall]}, target["project_token"]
    )
    assert result["errors"][0]["details"]["code"] == -1
    host.locked = False
    host.native_error = True
    result = await connector.dispatch(
        target["instance_id"], "tapir.CreateWalls", {"wallsData": [wall]}, target["project_token"]
    )
    assert result["errors"][0]["details"]["message"] == "No access right"


async def test_partial_failure_preserves_successes(host, connector, target, wall):
    host.partial = True
    result = await connector.dispatch(
        target["instance_id"],
        "tapir.CreateWalls",
        {"wallsData": [wall, copy.deepcopy(wall)]},
        target["project_token"],
    )
    assert result["status"] == "partial_failure"
    assert result["data"]["elements"][0]["elementId"]["guid"] in host.elements
    assert result["errors"][0]["path"] == ["elements", 1]
    assert not result["execution"]["atomic_batch"]


async def test_timeout_no_retry_and_write_hold(host, connector, target, wall):
    host.delay = 0.4
    args = {"wallsData": [wall]}
    result = await connector.dispatch(
        target["instance_id"], "tapir.CreateWalls", args, target["project_token"]
    )
    assert result["status"] == "outcome_unknown"
    assert host.mutations == 1
    again = await connector.dispatch(
        target["instance_id"], "tapir.CreateWalls", args, target["project_token"]
    )
    assert again["errors"][0]["code"] == "unresolved_outcome"
    assert host.mutations == 1
    await asyncio.sleep(0.25)
    assert len(host.elements) == 1  # The native mock completed after the client timed out.
    assert (await connector.connect(host.port))["unknown_operation"] == result["operation_id"]
    with pytest.raises(ConnectorError):
        await connector.acknowledge_unknown(target["instance_id"], result["operation_id"], False)
    await connector.acknowledge_unknown(target["instance_id"], result["operation_id"], True)
    assert connector.instance(target["instance_id"]).unknown_operation is None


async def test_invalid_response_after_write_is_unknown(host, connector, target, wall):
    host.bad_response = True
    result = await connector.dispatch(
        target["instance_id"], "tapir.CreateWalls", {"wallsData": [wall]}, target["project_token"]
    )
    assert result["status"] == "outcome_unknown"


async def test_serialized_mutations(connector, target, wall, host):
    host.delay = 0.04
    await asyncio.gather(
        *(
            connector.dispatch(
                target["instance_id"], "tapir.CreateWalls", {"wallsData": [wall]}, target["project_token"]
            )
            for _ in range(3)
        )
    )
    creates = [
        i
        for i, r in enumerate(host.requests)
        if r["parameters"].get("addOnCommandId", {}).get("commandName") == "CreateWalls"
    ]
    assert host.mutations == 3
    assert len(host.elements) == 3
    for i in creates:
        assert host.requests[i - 1]["parameters"]["addOnCommandId"]["commandName"] == "GetProjectInfo"


async def test_schema_support_probe(connector, target):
    result = await connector.command_schema("tapir.CreateWalls", target["instance_id"])
    assert result["support"] == "available"
    assert result["effect"] == "model"
    assert not result["dry_run"] and not result["exactly_once"]


@pytest.mark.parametrize("value", ["", "0", "65536", "19743-19723", "1-500", "x", "1-2-3"])
def test_invalid_port_configuration(value):
    with pytest.raises(ValueError):
        parse_ports(value)


def test_port_configuration():
    assert parse_ports("19723, 19724-19725,19723") == (19723, 19724, 19725)


async def test_unknown_command_and_null_never_forwarded(host, connector, target):
    before = len(host.requests)
    with pytest.raises(ConnectorError):
        await connector.dispatch(target["instance_id"], "official.ExecuteAddOnCommand", {})
    with pytest.raises(ConnectorError):
        await connector.dispatch(
            target["instance_id"], "tapir.GetElementsByType", {"elementType": "Wall", "filters": None}
        )
    assert len(host.requests) == before


async def test_archive_overwrite_and_empty_batch_refused(host, connector, target, tmp_path):
    archive = tmp_path / "existing.pla"
    archive.write_text("preserve")
    result = await connector.dispatch(
        target["instance_id"],
        "tapir.SaveProjectAsArchive",
        {"archiveFilePath": str(archive)},
        target["project_token"],
    )
    assert result["errors"][0]["code"] == "unsafe_file_target"
    assert archive.read_text() == "preserve"
    result = await connector.dispatch(
        target["instance_id"], "tapir.CreateWalls", {"wallsData": []}, target["project_token"]
    )
    assert result["errors"][0]["code"] == "invalid_arguments"
    assert host.mutations == 0


async def test_cancelled_wait_keeps_mutation_tracked(host, connector, target, wall):
    host.delay = 0.08
    caller = asyncio.create_task(
        connector.dispatch(
            target["instance_id"], "tapir.CreateWalls", {"wallsData": [wall]}, target["project_token"]
        )
    )
    while host.mutations == 0:
        await asyncio.sleep(0.005)
    caller.cancel()
    with pytest.raises(asyncio.CancelledError):
        await caller
    await asyncio.gather(*connector.background)
    assert len(host.elements) == 1
    assert list(connector.operations.values())[-1]["state"] == "succeeded"


async def test_nonfinite_host_response_after_write_is_unknown(host, connector, target, wall):
    native_respond = host.respond

    def nonfinite(body):
        reply = native_respond(body)
        if (
            body["command"] == "API.ExecuteAddOnCommand"
            and body["parameters"]["addOnCommandId"]["commandName"] == "CreateWalls"
        ):
            reply["result"]["addOnCommandResponse"]["badNumber"] = float("nan")
        return reply

    host.respond = nonfinite
    result = await connector.dispatch(
        target["instance_id"], "tapir.CreateWalls", {"wallsData": [wall]}, target["project_token"]
    )
    assert result["status"] == "outcome_unknown"
    assert result["errors"][0]["code"] == "invalid_response"
    assert host.mutations == 1
