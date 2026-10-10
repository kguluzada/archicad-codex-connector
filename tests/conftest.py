"""A real HTTP test host reproducing Archicad envelopes; never a native CAD substitute."""

import json
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

import pytest

from archicad_connector.service import Connector


class MockArchicad:
    def __init__(self):
        self.requests = []
        self.version = 30
        self.tapir_version = "1.7.0"
        self.missing_tapir = False
        self.unavailable_commands = set()
        self.project = {
            "isUntitled": False,
            "isTeamwork": False,
            "projectName": "Test",
            "projectPath": "C:\\test\\Test.pln",
            "projectLocation": "C:\\test\\Test.pln",
        }
        self.project_reads = 0
        self.switch_at = None
        self.delay = 0
        self.locked = False
        self.native_error = False
        self.bad_response = False
        self.mutations = 0
        self.elements = {}
        self.values = {}
        self.partial = False
        host = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                host.requests.append(body)
                reply = host.respond(body)
                encoded = json.dumps(reply).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                try:
                    self.wfile.write(encoded)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *_):
                pass

        self.http = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.http.server_address[1]
        self.thread = threading.Thread(target=self.http.serve_forever, daemon=True)
        self.thread.start()

    def close(self):
        self.http.shutdown()
        self.http.server_close()
        self.thread.join()

    def respond(self, body):
        command = body["command"]
        parameters = body.get("parameters", {})
        tapir = command == "API.ExecuteAddOnCommand"
        if tapir:
            command = parameters["addOnCommandId"]["commandName"]
            parameters = parameters["addOnCommandParameters"]
        else:
            command = command.removeprefix("API.")
        if command == "GetProductInfo":
            data = {"version": self.version, "buildNumber": 3000, "languageCode": "INT"}
        elif command == "IsAddOnCommandAvailable":
            name = parameters["addOnCommandId"]["commandName"]
            data = {"available": not self.missing_tapir and name not in self.unavailable_commands}
        elif command == "GetAddOnVersion":
            data = {"version": self.tapir_version}
        elif command == "GetProjectInfo":
            self.project_reads += 1
            if self.switch_at == self.project_reads:
                self.project = {**self.project, "projectName": "Other", "projectPath": "C:\\Other.pln"}
            data = dict(self.project)
        elif command in ("CreateWalls", "CreateSlabs", "SetPropertyValuesOfElements"):
            self.mutations += 1
            if self.delay:
                time.sleep(self.delay)
            if self.bad_response:
                return {"unexpected": True}
            if self.native_error:
                return {"succeeded": False, "error": {"code": -2130313204, "message": "No access right"}}
            if self.locked:
                data = (
                    {"error": {"code": -1, "message": "Locked or not reserved in Teamwork"}}
                    if tapir
                    else {
                        "executionResults": [{"success": False, "error": {"code": -1, "message": "Locked"}}]
                    }
                )
            elif command == "SetPropertyValuesOfElements":
                for value in parameters["elementPropertyValues"]:
                    self.values[(value["elementId"]["guid"], value["propertyId"]["guid"])] = value[
                        "propertyValue"
                    ]
                data = {"executionResults": [{"success": True} for _ in parameters["elementPropertyValues"]]}
            else:
                results = []
                kind, key = ("Wall", "wallsData") if command == "CreateWalls" else ("Slab", "slabsData")
                for index, payload in enumerate(parameters[key]):
                    if self.partial and index == 1:
                        results.append({"error": {"code": -1, "message": "Item locked"}})
                    else:
                        guid = str(uuid4())
                        self.elements[guid] = {"type": kind, "payload": payload}
                        results.append({"elementId": {"guid": guid}})
                data = {"elements": results}
        elif command in ("GetAllElements", "GetSelectedElements", "GetElementsByType"):
            data = {
                "elements": [
                    {"elementId": {"guid": guid}}
                    for guid, element in self.elements.items()
                    if command != "GetElementsByType" or element["type"] == parameters["elementType"]
                ]
            }
        elif command == "GetDetailsOfElements":
            data = {
                "detailsOfElements": [
                    {
                        "type": self.elements[e["elementId"]["guid"]]["type"],
                        "id": e["elementId"]["guid"],
                        "floorIndex": 0,
                        "layerIndex": 1,
                        "drawIndex": 1,
                        "details": self.elements[e["elementId"]["guid"]]["payload"],
                    }
                    for e in parameters["elements"]
                ]
            }
        elif command == "GetPropertyValuesOfElements":
            data = {
                "propertyValuesForElements": [
                    {
                        "propertyValues": [
                            {
                                "propertyValue": self.values.get(
                                    (e["elementId"]["guid"], p["propertyId"]["guid"]),
                                    {"type": "string", "status": "userUndefined"},
                                )
                            }
                            for p in parameters["properties"]
                        ]
                    }
                    for e in parameters["elements"]
                ]
            }
        elif command == "GetStories":
            data = {"stories": [{"index": 0, "name": "Ground", "level": 0.0}]}
        elif command == "IsAlive":
            data = {"isAlive": True}
        else:
            data = {"error": {"code": 404, "message": "Unsupported mock command"}}
            if not tapir:
                return {"succeeded": False, "error": data["error"]}
        return {"succeeded": True, "result": {"addOnCommandResponse": data} if tapir else data}


@pytest.fixture
def host():
    server = MockArchicad()
    try:
        yield server
    finally:
        server.close()


@pytest.fixture
async def connector(host):
    service = Connector([host.port], timeout=0.2)
    yield service
    await service.close()


@pytest.fixture
async def target(connector, host):
    return await connector.connect(host.port)


@pytest.fixture
def wall():
    return {
        "begCoordinate": {"x": 0.0, "y": 0.0},
        "endCoordinate": {"x": 5.0, "y": 0.0},
        "height": 3.0,
        "thickness": 0.2,
        "floorIndex": 0,
    }
