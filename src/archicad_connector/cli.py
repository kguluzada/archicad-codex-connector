"""MCP stdio server and a separate JSON diagnostic CLI."""

import argparse
import asyncio
import json
import logging
import os
import sys

from . import __version__
from .errors import ConnectorError
from .service import Connector


def parse_ports(value):
    ports = []
    for part in value.split(","):
        bounds = part.strip().split("-")
        if len(bounds) == 1:
            ports.append(int(bounds[0]))
        elif len(bounds) == 2:
            start, end = map(int, bounds)
            if end < start or end - start > 100:
                raise ValueError("Port ranges must be increasing and contain at most 101 ports.")
            ports.extend(range(start, end + 1))
        else:
            raise ValueError("Use comma-separated ports or start-end ranges.")
    if not ports or len(ports) > 101 or any(not 1 <= p <= 65535 for p in ports):
        raise ValueError("Use 1–101 ports, each between 1 and 65535.")
    return tuple(dict.fromkeys(ports))


async def diagnose(connector, port):
    try:
        discovery = await connector.discover()
        if port is not None:
            status = await connector.connect(port)
            result = {"status": "succeeded", "discovery": discovery, "target": status}
        else:
            result = {"status": "succeeded" if discovery["instances"] else "unavailable", **discovery}
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["status"] == "succeeded" else 1
    except ConnectorError as error:
        print(json.dumps({"status": "failed", "errors": [error.as_dict()]}))
        return 1
    finally:
        await connector.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Local Archicad/Tapir MCP connector")
    parser.add_argument("--version", action="version", version=__version__)
    parser.add_argument("--ports", default=os.environ.get("ARCHICAD_PORTS", "19723-19743"))
    parser.add_argument("--timeout", type=float, default=os.environ.get("ARCHICAD_TIMEOUT", "30"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("serve", help="MCP stdio; protocol output only on stdout")
    diagnostic = commands.add_parser("diagnose", help="Read-only host checks, JSON on stdout")
    diagnostic.add_argument("--port", type=int, help="Explicitly inspect one configured instance")
    args = parser.parse_args(argv)
    try:
        ports = parse_ports(args.ports)
        if not 0 < args.timeout <= 600:
            raise ValueError("Timeout must be >0 and <=600 seconds.")
    except ValueError as error:
        parser.error(str(error))
    logging.basicConfig(
        stream=sys.stderr, level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s"
    )
    connector = Connector(ports, args.timeout)
    if args.command == "diagnose":
        return asyncio.run(diagnose(connector, args.port))
    from .server import create_server

    create_server(connector).run(transport="stdio")
    return 0
