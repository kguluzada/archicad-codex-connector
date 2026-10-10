"""Loopback-only HTTP; one request attempt, separate official/Tapir envelopes."""

import json
import logging

import httpx

from .errors import ConnectorError

log = logging.getLogger(__name__)


def envelope(backend, name, arguments):
    if backend == "official":
        return {"command": "API." + name, "parameters": arguments}
    return {
        "command": "API.ExecuteAddOnCommand",
        "parameters": {
            "addOnCommandId": {"commandNamespace": "TapirCommand", "commandName": name},
            "addOnCommandParameters": arguments,
        },
    }


class ArchicadTransport:
    def __init__(self, timeout=30.0, probe_timeout=0.6):
        if timeout <= 0 or probe_timeout <= 0:
            raise ValueError("Timeouts must be positive.")
        self.timeout = timeout
        self.probe_timeout = probe_timeout
        self.http = httpx.AsyncClient(
            trust_env=False, follow_redirects=False, transport=httpx.AsyncHTTPTransport(retries=0)
        )

    async def close(self):
        await self.http.aclose()

    async def post(self, port, backend, name, arguments, *, mutation=False, probe=False):
        if type(port) is not int or not 1 <= port <= 65535:
            raise ConnectorError("invalid_port", "Use a valid local TCP port.")
        body = envelope(backend, name, arguments)
        log.debug("command=%s.%s port=%s", backend, name, port)
        try:
            response = await self.http.post(
                f"http://127.0.0.1:{port}/", json=body, timeout=self.probe_timeout if probe else self.timeout
            )
        except (httpx.ConnectError, httpx.ConnectTimeout, httpx.PoolTimeout) as error:
            raise ConnectorError(
                "unavailable", "No connection to Archicad. Start it and check the port."
            ) from error
        except httpx.HTTPError as error:
            raise ConnectorError(
                "transport_failure",
                "Archicad did not return a complete response. "
                "Inspect the model before considering another write.",
                outcome_unknown=mutation,
            ) from error
        if response.status_code != 200:
            raise ConnectorError(
                "http_error", f"Archicad HTTP status {response.status_code}.", outcome_unknown=mutation
            )
        try:
            reply = response.json()
            json.dumps(reply, allow_nan=False)
        except ValueError as error:
            raise ConnectorError(
                "invalid_response", "Archicad returned invalid JSON.", outcome_unknown=mutation
            ) from error
        if not isinstance(reply, dict) or type(reply.get("succeeded")) is not bool:
            raise ConnectorError(
                "invalid_response",
                "Expected the official succeeded/result/error envelope.",
                outcome_unknown=mutation,
            )
        if not reply["succeeded"]:
            raise ConnectorError(
                "host_error",
                "Archicad rejected the command. Check native error details; "
                "locked elements and Teamwork permissions can prevent edits.",
                details=reply.get("error"),
            )
        if not isinstance(reply.get("result"), dict):
            raise ConnectorError(
                "invalid_response", "Missing Archicad result object.", outcome_unknown=mutation
            )
        result = reply["result"]
        if backend == "tapir":
            result = result.get("addOnCommandResponse")
            if not isinstance(result, dict):
                raise ConnectorError(
                    "invalid_response", "Missing Tapir response object.", outcome_unknown=mutation
                )
            if "error" in result:
                raise ConnectorError(
                    "host_error",
                    "Tapir rejected the command. Check native error details.",
                    details=result["error"],
                )
        return result

    async def available(self, port, name):
        result = await self.post(
            port,
            "official",
            "IsAddOnCommandAvailable",
            {"addOnCommandId": {"commandNamespace": "TapirCommand", "commandName": name}},
        )
        if type(result.get("available")) is not bool:
            raise ConnectorError("invalid_response", "Invalid command availability response.")
        return result["available"]
