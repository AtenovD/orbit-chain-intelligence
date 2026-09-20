from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any

import httpx

from orchestrator.models import ProviderConnection
from orchestrator.security import secret_codec
from orchestrator.network_security import validate_outbound_url


PROTOCOL_VERSION = "2025-03-26"


class MCPError(RuntimeError):
    pass


def _request(method: str, params: dict[str, Any] | None = None, request_id: int = 1) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}


@dataclass(slots=True)
class MCPTool:
    name: str
    description: str
    input_schema: dict[str, Any]


class MCPClient:
    def __init__(self, connection: ProviderConnection) -> None:
        if connection.provider != "mcp":
            raise MCPError("Connection is not an MCP server")
        self.connection = connection
        self.config = connection.config or {}
        self.transport = str(self.config.get("transport", "streamable_http"))
        self.secret = secret_codec.decrypt(connection.api_key)

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if self.secret:
            header = str(self.config.get("auth_header", "Authorization"))
            prefix = str(self.config.get("auth_prefix", "Bearer"))
            headers[header] = f"{prefix} {self.secret}".strip()
        return headers

    @staticmethod
    def _decode_http(response: httpx.Response, payload: dict[str, Any]) -> dict[str, Any]:
        content_type = response.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            for line in response.text.splitlines():
                if line.startswith("data:"):
                    value = json.loads(line.removeprefix("data:").strip())
                    if value.get("id") == payload.get("id"):
                        return value
            raise MCPError("MCP SSE response did not contain a matching result")
        return response.json()

    async def _http_session(self, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        url = self.connection.base_url or self.config.get("url")
        if not url:
            raise MCPError("Remote MCP URL is missing")
        validate_outbound_url(str(url))
        async with httpx.AsyncClient(timeout=float(self.config.get("timeout_seconds", 30))) as client:
            headers = self._headers()
            response = await client.post(str(url), headers=headers, json=calls[0])
            response.raise_for_status()
            values = [self._decode_http(response, calls[0])]
            session_id = response.headers.get("mcp-session-id")
            if session_id:
                headers["Mcp-Session-Id"] = session_id
            notification = {"jsonrpc": "2.0", "method": "notifications/initialized"}
            initialized = await client.post(str(url), headers=headers, json=notification)
            if initialized.status_code not in {200, 202, 204}:
                initialized.raise_for_status()
            for call in calls[1:]:
                response = await client.post(str(url), headers=headers, json=call)
                response.raise_for_status()
                values.append(self._decode_http(response, call))
            return values

    async def _stdio_session(self, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        command = self.config.get("command")
        args = [str(item) for item in self.config.get("args", [])]
        if not command:
            raise MCPError("stdio MCP command is missing")
        env = os.environ.copy()
        secret_name = self.config.get("secret_name")
        if self.secret and secret_name:
            env[str(secret_name)] = self.secret
        process = await asyncio.create_subprocess_exec(
            str(command), *args,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        assert process.stdin and process.stdout
        results: list[dict[str, Any]] = []
        try:
            for index, call in enumerate(calls):
                process.stdin.write((json.dumps(call, ensure_ascii=False) + "\n").encode())
                await process.stdin.drain()
                line = await asyncio.wait_for(
                    process.stdout.readline(), timeout=float(self.config.get("timeout_seconds", 30))
                )
                if not line:
                    stderr = await process.stderr.read() if process.stderr else b""
                    raise MCPError(f"MCP process closed: {stderr.decode(errors='replace')[:500]}")
                results.append(json.loads(line))
                if index == 0:
                    process.stdin.write(
                        (json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n").encode()
                    )
                    await process.stdin.drain()
            return results
        finally:
            if process.returncode is None:
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=2)
                except TimeoutError:
                    process.kill()
                    await process.wait()

    async def _rpc_many(self, calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if self.transport == "stdio":
            return await self._stdio_session(calls)
        return await self._http_session(calls)

    @staticmethod
    def _unwrap(value: dict[str, Any]) -> dict[str, Any]:
        if value.get("error"):
            error = value["error"]
            raise MCPError(str(error.get("message") if isinstance(error, dict) else error))
        result = value.get("result")
        if not isinstance(result, dict):
            raise MCPError("MCP returned an invalid result")
        return result

    async def list_tools(self) -> list[MCPTool]:
        initialize = _request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "Orbit", "version": "0.2.0"},
            },
            1,
        )
        tools_call = _request("tools/list", {}, 2)
        values = await self._rpc_many([initialize, tools_call])
        self._unwrap(values[0])
        result = self._unwrap(values[1])
        return [
            MCPTool(
                name=str(item.get("name", "")),
                description=str(item.get("description", "")),
                input_schema=item.get("inputSchema") or {},
            )
            for item in result.get("tools", [])
            if item.get("name")
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        initialize = _request(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "Orbit", "version": "0.2.0"},
            },
            1,
        )
        call = _request("tools/call", {"name": name, "arguments": arguments}, 2)
        values = await self._rpc_many([initialize, call])
        self._unwrap(values[0])
        return self._unwrap(values[1])
