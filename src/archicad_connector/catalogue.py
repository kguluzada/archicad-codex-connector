"""A reviewed allowlist with unflattened native schemas and conservative effects."""

import copy
import json
from importlib.resources import files

from jsonschema import Draft7Validator, FormatChecker

from .errors import ConnectorError

TAPIR_VERSION = "1.7.0"


def obj(properties, required=()):
    return {
        "type": "object",
        "properties": properties,
        "required": list(required),
        "additionalProperties": False,
    }


def array(items):
    return {"type": "array", "items": items}


def enum(*values):
    return {"type": "string", "enum": list(values)}


GUID = obj({"guid": {"type": "string", "format": "uuid"}}, ["guid"])
ELEMENTS = array(obj({"elementId": GUID}, ["elementId"]))
PROPERTIES = array(obj({"propertyId": GUID}, ["propertyId"]))
# These are independently authored wire contracts checked against Graphisoft's documentation.
VALUE_TYPES = {
    "number": "number",
    "integer": "integer",
    "string": "string",
    "boolean": "boolean",
    "length": "number",
    "area": "number",
    "volume": "number",
    "angle": "number",
}
VALUE_SCHEMAS = []
for name, kind in VALUE_TYPES.items():
    for suffix in ("", "List"):
        schema = {"type": kind} if not suffix else array({"type": kind})
        VALUE_SCHEMAS.append(
            obj(
                {"type": enum(name + suffix), "status": enum("normal"), "value": schema},
                ["type", "status", "value"],
            )
        )
ENUM_ID = {
    "oneOf": [
        obj({"type": enum("displayValue"), "displayValue": {"type": "string"}}, ["type", "displayValue"]),
        obj(
            {"type": enum("nonLocalizedValue"), "nonLocalizedValue": {"type": "string"}},
            ["type", "nonLocalizedValue"],
        ),
    ]
}
for name, schema in [
    ("singleEnum", ENUM_ID),
    ("multiEnum", array(obj({"enumValueId": ENUM_ID}, ["enumValueId"]))),
]:
    VALUE_SCHEMAS.append(
        obj({"type": enum(name), "status": enum("normal"), "value": schema}, ["type", "status", "value"])
    )
VALUE_SCHEMAS.append(
    obj(
        {
            "type": enum(*VALUE_TYPES, *(x + "List" for x in VALUE_TYPES), "singleEnum", "multiEnum"),
            "status": enum("userUndefined"),
        },
        ["type", "status"],
    )
)
PROPERTY_VALUE = {"oneOf": VALUE_SCHEMAS}
PROPERTY_USER_ID = {
    "oneOf": [
        obj({"type": enum("BuiltIn"), "nonLocalizedName": {"type": "string"}}, ["type", "nonLocalizedName"]),
        obj(
            {
                "type": enum("UserDefined"),
                "localizedName": {"type": "array", "items": {"type": "string"}, "minItems": 2, "maxItems": 2},
            },
            ["type", "localizedName"],
        ),
    ]
}


class Catalogue:
    def __init__(self):
        vendor = json.loads(files("archicad_connector").joinpath("data/tapir.json").read_text())
        self.definitions = vendor["definitions"]
        self.commands = {c["id"]: c for c in vendor["commands"]}
        specs = {
            "GetProductInfo": ("Read host version, build, language.", obj({})),
            "IsAlive": ("Check Archicad JSON service.", obj({})),
            "GetAllElements": ("Read supported elements in the current plan.", obj({})),
            "GetSelectedElements": (
                "Read the selection in the current plan.",
                obj({"onlyEditable": {"type": "boolean"}, "onlySupportedTypes": {"type": "boolean"}}),
            ),
            "GetElementsByType": (
                "Query supported native element types in the plan.",
                obj(
                    {
                        "elementType": enum(
                            "All",
                            "Wall",
                            "Column",
                            "Beam",
                            "Window",
                            "Door",
                            "Object",
                            "Lamp",
                            "Slab",
                            "Roof",
                            "Mesh",
                            "Zone",
                            "CurtainWall",
                            "Shell",
                            "Skylight",
                            "Morph",
                            "Stair",
                            "Railing",
                            "Opening",
                        )
                    },
                    ["elementType"],
                ),
            ),
            "GetAllPropertyNames": ("List available property names.", obj({})),
            "GetPropertyIds": (
                "Resolve built-in or user-defined property names.",
                obj({"properties": array(PROPERTY_USER_ID)}, ["properties"]),
            ),
            "GetDetailsOfProperties": (
                "Inspect definition and editability of properties.",
                obj({"properties": PROPERTIES}, ["properties"]),
            ),
            "GetPropertyValuesOfElements": (
                "Read typed property values of native elements.",
                obj(
                    {
                        "elements": ELEMENTS,
                        "properties": PROPERTIES,
                        "onlySupportedTypes": {"type": "boolean"},
                    },
                    ["elements", "properties"],
                ),
            ),
            "SetPropertyValuesOfElements": (
                "Set normal or userUndefined values on explicit native elements.",
                obj(
                    {
                        "elementPropertyValues": array(
                            obj(
                                {"elementId": GUID, "propertyId": GUID, "propertyValue": PROPERTY_VALUE},
                                ["elementId", "propertyId", "propertyValue"],
                            )
                        )
                    },
                    ["elementPropertyValues"],
                ),
            ),
            "GetAllClassificationSystems": ("List classification systems.", obj({})),
            "GetClassificationsOfElements": (
                "Read assignments for explicit classification systems.",
                obj(
                    {
                        "elements": ELEMENTS,
                        "classificationSystemIds": array(
                            obj({"classificationSystemId": GUID}, ["classificationSystemId"])
                        ),
                    },
                    ["elements", "classificationSystemIds"],
                ),
            ),
        }
        for name, (description, schema) in specs.items():
            self.commands["official." + name] = {
                "id": "official." + name,
                "name": name,
                "backend": "official",
                "effect": "model" if name.startswith("Set") else "read",
                "description": description,
                "inputScheme": schema,
                "outputScheme": None,
                "group": "Graphisoft JSON",
                "version": "runtime-checked",
            }
        for command in self.commands:
            Draft7Validator.check_schema(self.schema(command))

    def get(self, command):
        if command not in self.commands:
            raise ConnectorError(
                "unsupported_command", "Command is outside the reviewed catalogue. Search commands."
            )
        return self.commands[command]

    def schema(self, command, output=False):
        native = self.get(command).get("outputScheme" if output else "inputScheme")
        if output and native is None:
            return None
        schema = copy.deepcopy(native) if native is not None else obj({})
        needed = {}

        def visit(node):
            if isinstance(node, dict):
                ref = node.get("$ref", "")
                if ref.startswith("#/definitions/"):
                    name = ref.removeprefix("#/definitions/")
                    if name not in needed:
                        needed[name] = copy.deepcopy(self.definitions[name])
                        visit(needed[name])
                for value in node.values():
                    visit(value)
            elif isinstance(node, list):
                for value in node:
                    visit(value)

        visit(schema)
        return {
            "$schema": "http://json-schema.org/draft-07/schema#",
            **schema,
            **({"definitions": needed} if needed else {}),
        }

    def validate(self, command, arguments):
        errors = sorted(
            Draft7Validator(self.schema(command), format_checker=FormatChecker()).iter_errors(arguments),
            key=lambda x: str(list(x.path)),
        )
        if errors:
            error = errors[0]
            # Do not echo the caller's values into diagnostic errors or logs.
            raise ConnectorError(
                "invalid_arguments",
                f"Schema violation at {list(error.path)}: {error.validator}",
                details={"path": list(error.path), "rule": error.validator},
            )
        json.dumps(arguments, allow_nan=False)

    def search(self, query="", offset=0, limit=20):
        if offset < 0 or not 1 <= limit <= 50:
            raise ConnectorError("invalid_arguments", "offset >= 0 and limit between 1 and 50 are required.")
        matches = [
            c
            for c in self.commands.values()
            if query.casefold() in (c["id"] + " " + c["description"]).casefold()
        ]
        return {
            "commands": [
                {k: c[k] for k in ("id", "backend", "description", "effect", "version")}
                for c in matches[offset : offset + limit]
            ],
            "total": len(matches),
            "next_offset": offset + limit if offset + limit < len(matches) else None,
        }
