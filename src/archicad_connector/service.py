"""Instance targeting, validation, project guards and mutation lifecycle."""

import asyncio
import hashlib
import json
import logging
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

from jsonschema import Draft7Validator

from .catalogue import TAPIR_VERSION, Catalogue
from .errors import ConnectorError
from .transport import ArchicadTransport

log = logging.getLogger(__name__)
PROJECT_WARNING = (
    "Observed fingerprint, not a native project/session identity. Closing and reopening the same "
    "path, replacing its file, or switching projects after the check can evade detection. "
    "Keep the target project active while editing."
)


@dataclass
class Instance:
    port: int
    instance_id: str = field(default_factory=lambda: uuid4().hex)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    unknown_operation: str | None = None


def project_token(instance, product, project):
    observed = {"instance_id": instance.instance_id, "product": product, "project": project}
    return hashlib.sha256(json.dumps(observed, sort_keys=True).encode()).hexdigest()


def item_errors(value, path=()):
    errors = []
    if isinstance(value, dict):
        if "error" in value:
            errors.append({"path": list(path), "native": value["error"]})
        elif value.get("success") is False:
            errors.append({"path": list(path), "native": {"message": "Native item failed without details."}})
        for key, item in value.items():
            if key != "error":
                errors.extend(item_errors(item, (*path, key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            errors.extend(item_errors(item, (*path, index)))
    return errors


class Connector:
    def __init__(self, ports=range(19723, 19744), timeout=30.0, transport=None):
        self.ports = tuple(ports)
        if not self.ports or any(type(p) is not int or not 1 <= p <= 65535 for p in self.ports):
            raise ValueError("Configure at least one valid local port.")
        self.transport = transport or ArchicadTransport(timeout)
        self.catalogue = Catalogue()
        self.instances = {}
        self.operations = OrderedDict()
        self.background = set()

    async def close(self):
        if self.background:
            await asyncio.gather(*self.background, return_exceptions=True)
        await self.transport.close()

    async def discover(self):
        async def probe(port):
            try:
                product = await self.transport.post(port, "official", "GetProductInfo", {}, probe=True)
                self._check_product(product)
                return {"port": port, "connection": "reachable", "archicad": product}
            except ConnectorError as error:
                return {"port": port, "connection": "unavailable", "error": error.as_dict()}

        probes = await asyncio.gather(*(probe(p) for p in self.ports))
        running = [p for p in probes if p["connection"] == "reachable"]
        return {
            "instances": running,
            "selection_required": True,
            "multiple_instances": len(running) > 1,
            "probes": probes,
        }

    @staticmethod
    def _check_product(product):
        if type(product.get("version")) is not int or type(product.get("buildNumber")) is not int:
            raise ConnectorError("invalid_response", "Invalid Archicad product information.")
        if not isinstance(product.get("languageCode"), str):
            raise ConnectorError("invalid_response", "Missing Archicad language code.")

    def instance(self, instance_id):
        if instance_id not in self.instances:
            raise ConnectorError("unknown_instance", "Connect explicitly to a discovered port first.")
        return self.instances[instance_id]

    async def connect(self, port):
        if type(port) is not int or port not in self.ports:
            raise ConnectorError("invalid_port", "Port is outside configured discovery ports.")
        instance = next((i for i in self.instances.values() if i.port == port), None)
        if instance is None:
            instance = Instance(port)
            self.instances[instance.instance_id] = instance
        return await self.status(instance.instance_id)

    async def _observe(self, instance):
        product = await self.transport.post(instance.port, "official", "GetProductInfo", {})
        self._check_product(product)
        tapir = None
        project = None
        warnings = [PROJECT_WARNING]
        if await self.transport.available(instance.port, "GetAddOnVersion"):
            version = await self.transport.post(instance.port, "tapir", "GetAddOnVersion", {})
            if not isinstance(version.get("version"), str):
                raise ConnectorError("invalid_response", "Invalid Tapir version response.")
            tapir = version["version"]
            if await self.transport.available(instance.port, "GetProjectInfo"):
                project = await self.transport.post(instance.port, "tapir", "GetProjectInfo", {})
                if type(project.get("isUntitled")) is not bool or type(project.get("isTeamwork")) is not bool:
                    raise ConnectorError("invalid_response", "Invalid Tapir project information.")
        else:
            warnings.append(
                "Tapir is unavailable. Official reads work; mutations require Tapir project checks."
            )
        compatible = 25 <= product["version"] <= 30 and tapir == TAPIR_VERSION
        if not compatible:
            warnings.append(
                "Native catalogue execution requires AC25–30 and Tapir 1.7.0; official reads "
                "remain available on AC25–30. This range is source-supported, not live-certified."
            )
        return {
            "instance_id": instance.instance_id,
            "port": instance.port,
            "connection": "reachable",
            "archicad": product,
            "tapir_version": tapir,
            "project": project,
            "project_token": project_token(instance, product, project) if project else None,
            "identity_kind": "observed_fingerprint",
            "native_catalogue_compatible": compatible,
            "unknown_operation": instance.unknown_operation,
            "warnings": warnings,
        }

    async def status(self, instance_id):
        instance = self.instance(instance_id)
        async with instance.lock:
            return await self._observe(instance)

    async def command_schema(self, command, instance_id=None):
        entry = self.catalogue.get(command)
        result = {k: entry[k] for k in ("id", "backend", "name", "effect", "version", "description")}
        result.update(
            input_schema=self.catalogue.schema(command),
            output_schema=self.catalogue.schema(command, output=True),
            support="not_checked",
            units="SI: metres, square/cubic metres, radians",
            coordinates="Archicad project coordinates; no UCS/geo/unit conversion",
            atomic_batch=False,
            cancellation=False,
            dry_run=False,
            exactly_once=False,
        )
        if entry["effect"] == "files":
            result["side_effects"] = ["writes archive file", "changes active project (Save As)"]
        if instance_id:
            instance = self.instance(instance_id)
            async with instance.lock:
                observed = await self._observe(instance)
                if not 25 <= observed["archicad"]["version"] <= 30:
                    result["support"] = "unsupported_archicad_version"
                elif entry["backend"] == "tapir":
                    result["support"] = (
                        "available"
                        if observed["native_catalogue_compatible"]
                        and await self.transport.available(instance.port, entry["name"])
                        else "unavailable_or_version_mismatch"
                    )
                else:
                    result["support"] = "host_checked_on_execution"
        return result

    async def dispatch(self, instance_id, command, arguments, expected_project=None):
        entry = self.catalogue.get(command)
        try:
            self.catalogue.validate(command, arguments)
        except (ValueError, TypeError) as error:
            raise ConnectorError("invalid_arguments", "Arguments must contain finite JSON values.") from error
        instance = self.instance(instance_id)
        mutation = entry["effect"] != "read"
        if mutation and not expected_project:
            raise ConnectorError(
                "project_target_required", "Pass the project_token from connect/status explicitly."
            )
        operation_id = uuid4().hex
        operation = {
            "operation_id": operation_id,
            "command": command,
            "instance_id": instance_id,
            "effect": entry["effect"],
            "state": "queued",
        }
        self.operations[operation_id] = operation
        self._prune_operations()
        # Keep dispatched work tracked even if the MCP caller disconnects/cancels its wait.
        task = asyncio.create_task(self._execute(instance, entry, arguments, expected_project, operation))
        self.background.add(task)
        task.add_done_callback(self.background.discard)
        return await asyncio.shield(task)

    def _prune_operations(self):
        for key, value in list(self.operations.items()):
            if len(self.operations) <= 100:
                break
            if value["state"] not in ("queued", "running", "outcome_unknown") or value.get(
                "acknowledged_after_inspection"
            ):
                del self.operations[key]

    async def _execute(self, instance, entry, arguments, expected_project, operation):
        mutation = entry["effect"] != "read"
        try:
            async with instance.lock:
                if mutation and instance.unknown_operation:
                    raise ConnectorError(
                        "unresolved_outcome",
                        "An earlier mutation has an unknown outcome. "
                        "Inspect the model, then explicitly acknowledge it.",
                        details={"operation_id": instance.unknown_operation},
                    )
                observed = await self._observe(instance)
                if not 25 <= observed["archicad"]["version"] <= 30:
                    raise ConnectorError(
                        "unsupported_version", "Only AC25–30 wire contracts have been reviewed."
                    )
                if entry["backend"] == "tapir":
                    if observed["tapir_version"] is None:
                        raise ConnectorError(
                            "missing_tapir", "Install matching Tapir 1.7.0 and restart Archicad."
                        )
                    if observed["tapir_version"] != TAPIR_VERSION:
                        raise ConnectorError("unsupported_version", "Tapir schemas are pinned to 1.7.0.")
                    if not await self.transport.available(instance.port, entry["name"]):
                        raise ConnectorError(
                            "unsupported_command", "This command is not registered in the host."
                        )
                if mutation:
                    self._validate_mutation(entry, arguments)
                    if not observed["project"]:
                        raise ConnectorError(
                            "missing_project", "Tapir project information is required for writes."
                        )
                    if observed["project"]["isUntitled"] or not observed["project"].get("projectPath"):
                        raise ConnectorError(
                            "unsafe_project_target",
                            "Save the project before writing; untitled "
                            "projects cannot be distinguished reliably.",
                        )
                    # Final native observation immediately before dispatch, after all other checks.
                    project = await self.transport.post(instance.port, "tapir", "GetProjectInfo", {})
                    if (
                        project != observed["project"]
                        or project_token(instance, observed["archicad"], project) != expected_project
                    ):
                        raise ConnectorError(
                            "project_changed",
                            "Project changed before execution. Reinspect and pass its current project_token.",
                        )
                operation["state"] = "running"
                log.info(
                    "operation=%s command=%s port=%d state=running",
                    operation["operation_id"],
                    entry["id"],
                    instance.port,
                )
                data = await self.transport.post(
                    instance.port, entry["backend"], entry["name"], arguments, mutation=mutation
                )
                errors = item_errors(data)
                warnings = []
                output = self.catalogue.schema(entry["id"], output=True)
                if output and not Draft7Validator(output).is_valid(data):
                    warnings.append(
                        "Native response differs from the documented success schema; raw data preserved."
                    )
                state = "partial_failure" if errors else "succeeded"
                operation["state"] = state
                return {
                    **operation,
                    "status": state,
                    "data": data,
                    "errors": errors,
                    "warnings": warnings,
                    "execution": {
                        "atomic_batch": False,
                        "automatic_retry": False,
                        "undo": "native Undo entry in Tapir source, live-unverified"
                        if entry["name"] in ("CreateWalls", "CreateSlabs")
                        else "not_verified",
                        "rollback": "not_implemented",
                        "cancellation": "not_implemented",
                    },
                }
        except ConnectorError as error:
            operation["state"] = "outcome_unknown" if error.outcome_unknown else "failed"
            if error.outcome_unknown:
                instance.unknown_operation = operation["operation_id"]
            return {
                **operation,
                "status": operation["state"],
                "data": None,
                "errors": [error.as_dict()],
                "warnings": ["Do not retry writes blindly."] if mutation else [],
            }

    @staticmethod
    def _validate_mutation(entry, arguments):
        name = entry["name"]
        if name in ("CreateWalls", "CreateSlabs"):
            key = "wallsData" if name == "CreateWalls" else "slabsData"
            if not arguments[key]:
                raise ConnectorError("invalid_arguments", "Creation batch must contain at least one item.")
        if name == "CreateWalls":
            for wall in arguments["wallsData"]:
                if wall["begCoordinate"] == wall["endCoordinate"]:
                    raise ConnectorError("invalid_geometry", "Wall endpoints must differ.")
        if name == "SetPropertyValuesOfElements" and not arguments["elementPropertyValues"]:
            raise ConnectorError("invalid_arguments", "Property update must identify at least one element.")
        if name == "SaveProjectAsArchive":
            path = Path(arguments["archiveFilePath"])
            if not path.is_absolute() or path.suffix.lower() != ".pla" or path.exists():
                raise ConnectorError(
                    "unsafe_file_target",
                    "Use an absolute, new .pla path. Existing files "
                    "are refused because the host overwrites them.",
                )

    def operation_status(self, operation_id):
        if operation_id not in self.operations:
            raise ConnectorError("unknown_operation", "No retained operation with this ID in this process.")
        return dict(self.operations[operation_id])

    async def acknowledge_unknown(self, instance_id, operation_id, model_inspected):
        instance = self.instance(instance_id)
        async with instance.lock:
            if model_inspected is not True or instance.unknown_operation != operation_id:
                raise ConnectorError(
                    "invalid_acknowledgement",
                    "Inspect the model and acknowledge the current unknown operation explicitly.",
                )
            self.operations[operation_id]["acknowledged_after_inspection"] = True
            instance.unknown_operation = None
            return {
                "status": "acknowledged",
                "operation_id": operation_id,
                "warnings": ["Acknowledgement does not prove completion or failure."],
            }
