from __future__ import annotations

import json
import os
import base64
import hashlib
import secrets
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from queue import Empty, Queue
from typing import Any


class AkiflowServiceError(RuntimeError):
    pass


@dataclass
class _McpResponse:
    id: int | None
    result: Any = None
    error: Any = None


class AkiflowService:
    """Small MCP client wrapper for Akiflow proof-of-concept calls."""

    def __init__(self) -> None:
        self.http_url = os.getenv("AKIFLOW_MCP_URL", "https://mcp.akiflow.com/mcp")
        self.command = os.getenv("AKIFLOW_MCP_COMMAND")
        self.bearer_token = os.getenv("AKIFLOW_MCP_BEARER_TOKEN")
        self.test_tool = os.getenv("AKIFLOW_MCP_TEST_TOOL", "list_tasks")
        self.create_task_tool = os.getenv("AKIFLOW_MCP_CREATE_TASK_TOOL", "create_task")
        self.timeout_seconds = float(os.getenv("AKIFLOW_MCP_TIMEOUT_SECONDS", "10"))
        self.authorization_endpoint = os.getenv("AKIFLOW_AUTHORIZATION_ENDPOINT", "https://web.akiflow.com/oauth/authorize")
        self.token_endpoint = os.getenv("AKIFLOW_TOKEN_ENDPOINT", "https://web.akiflow.com/oauth/token")
        self.registration_endpoint = os.getenv("AKIFLOW_REGISTRATION_ENDPOINT", "https://web.akiflow.com/oauth/register")
        self.public_base_url = os.getenv("OPERATOR_PUBLIC_BASE_URL", "http://127.0.0.1:8000")
        self.client_id = os.getenv("AKIFLOW_OAUTH_CLIENT_ID")
        self._oauth_states: dict[str, str] = {}

    def authorization_url(self) -> str:
        client_id = self._client_id()
        code_verifier = self._code_verifier()
        state = secrets.token_urlsafe(24)
        self._oauth_states[state] = code_verifier

        query = urllib.parse.urlencode(
            {
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": self.redirect_uri,
                "scope": "mcp:read mcp:write",
                "state": state,
                "code_challenge": self._code_challenge(code_verifier),
                "code_challenge_method": "S256",
            }
        )
        return f"{self.authorization_endpoint}?{query}"

    def complete_oauth_callback(self, code: str, state: str) -> dict[str, Any]:
        code_verifier = self._oauth_states.pop(state, None)
        if not code_verifier:
            raise AkiflowServiceError("OAuth state was not recognized. Please start Akiflow login again.")

        payload = urllib.parse.urlencode(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": self.redirect_uri,
                "client_id": self._client_id(),
                "code_verifier": code_verifier,
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self.token_endpoint,
            data=payload,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "User-Agent": "OperatorLocalPOC/0.1",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                token_response = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover - depends on Akiflow OAuth availability.
            raise AkiflowServiceError(f"Akiflow OAuth token exchange failed: {exc}") from exc

        access_token = token_response.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise AkiflowServiceError("Akiflow OAuth token response did not include an access token.")

        self.bearer_token = access_token
        return {
            "ok": True,
            "token_type": token_response.get("token_type"),
            "scope": token_response.get("scope"),
            "expires_in": token_response.get("expires_in"),
        }

    @property
    def redirect_uri(self) -> str:
        return f"{self.public_base_url.rstrip('/')}/akiflow/oauth/callback"

    def test_connection(self) -> dict[str, Any]:
        result = self._call_tool(self.test_tool, {"status": "inbox"})
        return {
            "ok": True,
            "transport": self._transport_name(),
            "tool": self.test_tool,
            "result": result,
        }

    def create_test_task(self) -> dict[str, Any]:
        result = self._call_tool(
            self.create_task_tool,
            {
                "title": "Operator MCP Test",
                "status": "inbox",
                "description": "Created by Operator via the local Akiflow MCP proof of concept.",
            },
        )
        return {
            "ok": True,
            "transport": self._transport_name(),
            "tool": self.create_task_tool,
            "result": result,
        }

    def _transport_name(self) -> str:
        if self.http_url:
            return "http"
        if self.command:
            return "stdio"

        return "unconfigured"

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        try:
            if self.http_url:
                return self._call_tool_http(name, arguments)
            if self.command:
                return self._call_tool_stdio(name, arguments)
        except AkiflowServiceError as exc:
            if name.startswith("_") and "Unknown tool" in str(exc):
                return self._call_tool(name.removeprefix("_"), arguments)

            raise

        raise AkiflowServiceError(
            "Akiflow MCP is not configured. Set AKIFLOW_MCP_URL or AKIFLOW_MCP_COMMAND."
        )

    def _client_id(self) -> str:
        if self.client_id:
            return self.client_id

        payload = {
            "client_name": "Operator Local POC",
            "redirect_uris": [self.redirect_uri],
            "grant_types": ["authorization_code", "refresh_token"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": "mcp:read mcp:write",
        }
        request = urllib.request.Request(
            self.registration_endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "OperatorLocalPOC/0.1",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                registration = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover - depends on Akiflow OAuth availability.
            raise AkiflowServiceError(f"Akiflow OAuth client registration failed: {exc}") from exc

        client_id = registration.get("client_id")
        if not isinstance(client_id, str) or not client_id:
            raise AkiflowServiceError("Akiflow OAuth registration did not return a client_id.")

        self.client_id = client_id
        return client_id

    def _code_verifier(self) -> str:
        return secrets.token_urlsafe(64)

    def _code_challenge(self, code_verifier: str) -> str:
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def _call_tool_http(self, name: str, arguments: dict[str, Any]) -> Any:
        session_id: str | None = None
        init_response, session_id = self._http_rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "operator", "version": "0.1.0"},
            },
            request_id=1,
            session_id=session_id,
        )
        self._raise_for_error(init_response)

        self._http_rpc("notifications/initialized", {}, request_id=None, session_id=session_id)

        call_response, _ = self._http_rpc(
            "tools/call",
            {"name": name, "arguments": arguments},
            request_id=2,
            session_id=session_id,
        )
        self._raise_for_error(call_response)
        return call_response.result

    def _http_rpc(
        self,
        method: str,
        params: dict[str, Any],
        request_id: int | None,
        session_id: str | None,
    ) -> tuple[_McpResponse, str | None]:
        if not self.http_url:
            raise AkiflowServiceError("AKIFLOW_MCP_URL is not configured.")

        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params}
        if request_id is not None:
            payload["id"] = request_id

        headers = {
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
            "User-Agent": "OperatorLocalPOC/0.1",
        }
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        if session_id:
            headers["Mcp-Session-Id"] = session_id

        request = urllib.request.Request(
            self.http_url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = response.read().decode("utf-8")
                next_session_id = response.headers.get("Mcp-Session-Id") or session_id
        except Exception as exc:  # pragma: no cover - network shape depends on local MCP server.
            raise AkiflowServiceError(f"Akiflow MCP HTTP request failed: {exc}") from exc

        if request_id is None:
            return _McpResponse(id=None, result={"accepted": True}), next_session_id

        return self._parse_rpc_body(body), next_session_id

    def _call_tool_stdio(self, name: str, arguments: dict[str, Any]) -> Any:
        if not self.command:
            raise AkiflowServiceError("AKIFLOW_MCP_COMMAND is not configured.")

        process = subprocess.Popen(
            self.command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            shell=True,
        )
        responses: Queue[str] = Queue()

        def read_stdout() -> None:
            assert process.stdout is not None
            for line in process.stdout:
                if line.strip():
                    responses.put(line)

        threading.Thread(target=read_stdout, daemon=True).start()

        try:
            init_response = self._stdio_request(
                process,
                responses,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "initialize",
                    "params": {
                        "protocolVersion": "2024-11-05",
                        "capabilities": {},
                        "clientInfo": {"name": "operator", "version": "0.1.0"},
                    },
                },
            )
            self._raise_for_error(init_response)
            self._stdio_notify(process, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})

            call_response = self._stdio_request(
                process,
                responses,
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                },
            )
            self._raise_for_error(call_response)
            return call_response.result
        finally:
            process.terminate()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()

    def _stdio_request(self, process: subprocess.Popen[str], responses: Queue[str], payload: dict[str, Any]) -> _McpResponse:
        self._stdio_write(process, payload)
        deadline = time.monotonic() + self.timeout_seconds

        while time.monotonic() < deadline:
            try:
                line = responses.get(timeout=0.1)
            except Empty:
                continue

            message = json.loads(line)
            if message.get("id") == payload.get("id"):
                return _McpResponse(
                    id=message.get("id"),
                    result=message.get("result"),
                    error=message.get("error"),
                )

        raise AkiflowServiceError(f"Timed out waiting for MCP response to {payload['method']}.")

    def _stdio_notify(self, process: subprocess.Popen[str], payload: dict[str, Any]) -> None:
        self._stdio_write(process, payload)

    def _stdio_write(self, process: subprocess.Popen[str], payload: dict[str, Any]) -> None:
        if process.stdin is None:
            raise AkiflowServiceError("Akiflow MCP stdio process is not writable.")

        process.stdin.write(json.dumps(payload) + "\n")
        process.stdin.flush()

    def _parse_rpc_body(self, body: str) -> _McpResponse:
        text = body.strip()
        if text.startswith("event:") or "\ndata:" in text:
            data_lines = [line[5:].strip() for line in text.splitlines() if line.startswith("data:")]
            text = "\n".join(data_lines)

        try:
            message = json.loads(text)
        except json.JSONDecodeError as exc:
            raise AkiflowServiceError(f"Could not parse MCP response: {body}") from exc

        return _McpResponse(id=message.get("id"), result=message.get("result"), error=message.get("error"))

    def _raise_for_error(self, response: _McpResponse) -> None:
        if response.error:
            raise AkiflowServiceError(json.dumps(response.error))
