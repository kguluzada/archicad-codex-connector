"""Extract an audited allowlist from MIT Tapir 1.7.0 documentation; never execute JS."""

import hashlib
import json
import re
import urllib.request
from pathlib import Path

COMMIT = "02691b5d680b60c73317e8e49b78ab14dfd4c9d8"
BASE = f"https://raw.githubusercontent.com/ENZYME-APD/tapir-archicad-automation/{COMMIT}/"
DEST = Path(__file__).resolve().parents[1] / "src/archicad_connector/data"
EFFECTS = {
    "GetAddOnVersion": "read",
    "GetProjectInfo": "read",
    "GetStories": "read",
    "GetSelectedElements": "read",
    "GetElementsByType": "read",
    "GetAllElements": "read",
    "FilterElements": "read",
    "GetDetailsOfElements": "read",
    "GetAllProperties": "read",
    "GetAttributesByType": "read",
    "GetLayers": "read",
    "GetBuildingMaterials": "read",
    "GetClassificationsOfElements": "read",
    "GetCurrentWindowType": "read",
    "CreateWalls": "model",
    "CreateSlabs": "model",
    "ChangeSelectionOfElements": "application",
    "SaveProjectAsArchive": "files",
}


def load_js(raw):
    return json.loads(re.sub(r"^\s*var \w+\s*=\s*", "", raw.decode("utf-8-sig")).strip().removesuffix(";"))


def local_refs(node):
    if isinstance(node, list):
        return [local_refs(x) for x in node]
    if isinstance(node, dict):
        return {
            k: (v.replace("#/", "#/definitions/", 1) if k == "$ref" else local_refs(v))
            for k, v in node.items()
        }
    return node


def main():
    hashes = {}
    parsed = []
    for name in ("command_definitions.js", "common_schema_definitions.js"):
        raw = urllib.request.urlopen(BASE + "docs/archicad-addon/" + name, timeout=30).read()
        hashes[name] = hashlib.sha256(raw).hexdigest()
        parsed.append(load_js(raw))
    commands, definitions = parsed
    entries = []
    for group in commands:
        for command in group["commands"]:
            if command["name"] in EFFECTS:
                entries.append(
                    {
                        "id": "tapir." + command["name"],
                        "backend": "tapir",
                        "name": command["name"],
                        "group": group["name"],
                        "effect": EFFECTS[command["name"]],
                        **command,
                    }
                )
    assert {c["name"] for c in entries} == set(EFFECTS)
    DEST.mkdir(parents=True, exist_ok=True)
    data = {
        "release": "1.7.0",
        "commit": COMMIT,
        "source_sha256": hashes,
        "commands": local_refs(entries),
        "definitions": local_refs(definitions),
    }
    (DEST / "tapir.json").write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"Vendored {len(entries)} audited Tapir commands from {COMMIT}")


if __name__ == "__main__":
    main()
