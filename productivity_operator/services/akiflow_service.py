from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import subprocess
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from productivity_operator.task_registry import OperatorTask


class AkiflowServiceError(RuntimeError):
    pass


@dataclass
class _McpResponse:
    id: int | None
    result: Any = None
    error: Any = None


class AkiflowService:
    """Production boundary for all Akiflow MCP communication."""

    SCHEDULED_START_KEYS = [
        "start",
        "start_time",
        "startTime",
        "start_datetime",
        "startDatetime",
        "datetime",
        "date",
        "planned_at",
        "plannedAt",
        "planned_for",
        "plannedFor",
        "scheduled_at",
        "scheduledAt",
        "scheduled_start",
        "scheduledStart",
    ]

    def __init__(self) -> None:
        self.http_url = os.getenv("AKIFLOW_MCP_URL", "https://mcp.akiflow.com/mcp")
        self.command = os.getenv("AKIFLOW_MCP_COMMAND")
        self.bearer_token = os.getenv("AKIFLOW_MCP_BEARER_TOKEN")
        self.timeout_seconds = float(os.getenv("AKIFLOW_MCP_TIMEOUT_SECONDS", "10"))
        self.authorization_endpoint = os.getenv("AKIFLOW_AUTHORIZATION_ENDPOINT", "https://web.akiflow.com/oauth/authorize")
        self.token_endpoint = os.getenv("AKIFLOW_TOKEN_ENDPOINT", "https://web.akiflow.com/oauth/token")
        self.registration_endpoint = os.getenv("AKIFLOW_REGISTRATION_ENDPOINT", "https://web.akiflow.com/oauth/register")
        self.public_base_url = os.getenv("OPERATOR_PUBLIC_BASE_URL", "http://127.0.0.1:8000")
        self.client_id = os.getenv("AKIFLOW_OAUTH_CLIENT_ID")
        self.token_cache_path = Path(os.getenv("AKIFLOW_TOKEN_CACHE_PATH", ".operator/akiflow_token.json"))
        self.refresh_token: str | None = None
        self.token_expires_at: float | None = None
        self._oauth_states: dict[str, str] = {}
        self._load_token_cache()

    def authorization_url(self) -> str:
        client_id = self._client_id()
        code_verifier = secrets.token_urlsafe(64)
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
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Operator/0.3",
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
        self.refresh_token = self._optional_token(token_response.get("refresh_token")) or self.refresh_token
        self.token_expires_at = self._expires_at(token_response.get("expires_in"))
        self._save_token_cache(token_response)
        return {
            "ok": True,
            "token_type": token_response.get("token_type"),
            "scope": token_response.get("scope"),
            "expires_in": token_response.get("expires_in"),
        }

    def auth_status(self) -> dict[str, Any]:
        if not self.bearer_token:
            return {
                "connected": False,
                "message": "Akiflow is not connected. Please connect Akiflow.",
            }
        if self._token_is_expired() and not self.refresh_token:
            return {
                "connected": False,
                "expires_at": self.token_expires_at,
                "message": "Akiflow login expired. Please connect Akiflow again.",
            }
        if self._token_is_expired() and self.refresh_token:
            return {
                "connected": True,
                "expires_at": self.token_expires_at,
                "message": "Akiflow token is expired; Operator will try to refresh it on the next request.",
            }
        return {
            "connected": True,
            "expires_at": self.token_expires_at,
            "message": "Akiflow is connected.",
        }

    @property
    def redirect_uri(self) -> str:
        return f"{self.public_base_url.rstrip('/')}/akiflow/oauth/callback"

    def get_today_tasks(self) -> list[dict[str, Any]]:
        today = date.today().isoformat()
        result = self._call_first_available_tool(
            [
                (
                    "get_schedule",
                    {
                        "start_date": today,
                        "end_date": today,
                        "entities": "tasks",
                        "overdue_mode": "with_overdue",
                        "completed_mode": "no_completed",
                        "sort": "startTime",
                    },
                ),
                ("list_tasks", {"status": "inbox"}),
            ]
        )
        return self._normalize_tasks(result)

    def sync_tasks(self, start_date: str, end_date: str) -> list[OperatorTask]:
        result = self._call_tool(
            "get_schedule",
            {
                "start_date": start_date,
                "end_date": end_date,
                "entities": "tasks",
                "completed_mode": "no_completed",
                "overdue_mode": "with_overdue",
                "sort": "startTime",
            },
        )
        return self._normalize_operator_tasks(result)

    def get_today_schedule(self) -> list[dict[str, Any]]:
        today = date.today().isoformat()
        result = self._call_first_available_tool(
            [
                (
                    "get_schedule",
                    {
                        "start_date": today,
                        "end_date": today,
                        "entities": "events",
                        "sort": "startTime",
                    },
                ),
                (
                    "get_schedule",
                    {
                        "start_date": today,
                        "end_date": today,
                        "entities": "all",
                        "sort": "startTime",
                    },
                ),
            ]
        )
        return self._normalize_schedule(result)

    def complete_task(self, task_id: str) -> dict[str, Any]:
        if not task_id:
            raise AkiflowServiceError("task_id is required.")

        return {
            "ok": True,
            "task_id": task_id,
            "result": self._call_tool("complete_task", {"task_id": task_id}),
        }

    def plan_task(self, task_id: str, start_datetime: str) -> dict[str, Any]:
        if not task_id:
            raise AkiflowServiceError("task_id is required.")
        if not start_datetime:
            raise AkiflowServiceError("start_datetime is required.")

        return {
            "ok": True,
            "task_id": task_id,
            "start_datetime": start_datetime,
            "result": self._call_tool(
                "plan_task",
                {
                    "task_id": task_id,
                    "start_datetime": start_datetime,
                },
            ),
        }

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        if self.http_url:
            response = self._mcp_request_http("tools/call", {"name": name, "arguments": arguments})
            self._raise_for_error(response)
            return response.result
        if self.command:
            response = self._mcp_request_stdio("tools/call", {"name": name, "arguments": arguments})
            self._raise_for_error(response)
            return response.result

        raise AkiflowServiceError("Akiflow MCP is not configured. Set AKIFLOW_MCP_URL or AKIFLOW_MCP_COMMAND.")

    def _client_id(self) -> str:
        if self.client_id:
            return self.client_id

        payload = {
            "client_name": "Operator",
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
                "Accept": "application/json",
                "Content-Type": "application/json",
                "User-Agent": "Operator/0.3",
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

    def _code_challenge(self, code_verifier: str) -> str:
        digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
        return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")

    def _ensure_token_valid(self) -> None:
        if not self._token_is_expired():
            return
        if not self.refresh_token:
            raise AkiflowServiceError("Akiflow login expired. Please connect Akiflow again.")
        self._refresh_access_token()

    def _refresh_access_token(self) -> None:
        if not self.refresh_token:
            raise AkiflowServiceError("Akiflow login expired. Please connect Akiflow again.")

        payload = urllib.parse.urlencode(
            {
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": self._client_id(),
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            self.token_endpoint,
            data=payload,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "Operator/0.3",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                token_response = json.loads(response.read().decode("utf-8"))
        except Exception as exc:  # pragma: no cover - depends on Akiflow OAuth availability.
            self.bearer_token = None
            raise AkiflowServiceError("Akiflow login expired. Please connect Akiflow again.") from exc

        access_token = token_response.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            self.bearer_token = None
            raise AkiflowServiceError("Akiflow token refresh did not return an access token. Please connect Akiflow again.")

        self.bearer_token = access_token
        self.refresh_token = self._optional_token(token_response.get("refresh_token")) or self.refresh_token
        self.token_expires_at = self._expires_at(token_response.get("expires_in"))
        self._save_token_cache(token_response)

    def _load_token_cache(self) -> None:
        if self.bearer_token or not self.token_cache_path.exists():
            return
        try:
            data = json.loads(self.token_cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return

        self.bearer_token = self._optional_token(data.get("access_token"))
        self.refresh_token = self._optional_token(data.get("refresh_token"))
        if not self.client_id:
            self.client_id = self._optional_token(data.get("client_id"))
        expires_at = data.get("expires_at")
        if isinstance(expires_at, (int, float)):
            self.token_expires_at = float(expires_at)

    def _save_token_cache(self, token_response: dict[str, Any]) -> None:
        self.token_cache_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "access_token": self.bearer_token,
            "refresh_token": self.refresh_token,
            "expires_at": self.token_expires_at,
            "client_id": self.client_id,
            "scope": token_response.get("scope"),
            "token_type": token_response.get("token_type"),
            "saved_at": time.time(),
        }
        self.token_cache_path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def _optional_token(self, value: Any) -> str | None:
        return value if isinstance(value, str) and value else None

    def _expires_at(self, expires_in: Any) -> float | None:
        try:
            seconds = int(expires_in)
        except (TypeError, ValueError):
            return None
        return time.time() + max(0, seconds)

    def _token_is_expired(self) -> bool:
        if self.token_expires_at is None:
            return False
        return time.time() >= self.token_expires_at - 60

    def _call_first_available_tool(self, calls: list[tuple[str, dict[str, Any]]]) -> Any:
        errors: list[str] = []
        for name, arguments in calls:
            try:
                return self._call_tool(name, arguments)
            except AkiflowServiceError as exc:
                message = str(exc)
                if "Unknown tool" in message or "Invalid arguments" in message:
                    errors.append(message)
                    continue
                raise

        raise AkiflowServiceError("; ".join(errors) or "No Akiflow MCP tool worked.")

    def _mcp_request_http(self, method: str, params: dict[str, Any]) -> _McpResponse:
        session_id: str | None = None
        init_response, session_id = self._http_rpc(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "operator", "version": "0.3.0"},
            },
            request_id=1,
            session_id=session_id,
        )
        self._raise_for_error(init_response)

        self._http_rpc("notifications/initialized", {}, request_id=None, session_id=session_id)
        call_response, _ = self._http_rpc(method, params, request_id=2, session_id=session_id)
        return call_response

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
            "User-Agent": "Operator/0.3",
        }
        self._ensure_token_valid()
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
        except Exception as exc:  # pragma: no cover - depends on Akiflow availability.
            raise AkiflowServiceError(f"Akiflow MCP HTTP request failed: {exc}") from exc

        if request_id is None:
            return _McpResponse(id=None, result={"accepted": True}), next_session_id

        return self._parse_rpc_body(body), next_session_id

    def _mcp_request_stdio(self, method: str, params: dict[str, Any]) -> _McpResponse:
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
                        "clientInfo": {"name": "operator", "version": "0.3.0"},
                    },
                },
            )
            self._raise_for_error(init_response)
            self._stdio_write(process, {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
            return self._stdio_request(
                process,
                responses,
                {"jsonrpc": "2.0", "id": 2, "method": method, "params": params},
            )
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
                return _McpResponse(id=message.get("id"), result=message.get("result"), error=message.get("error"))

        raise AkiflowServiceError(f"Timed out waiting for MCP response to {payload['method']}.")

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

    def _normalize_tasks(self, result: Any) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in self._extract_items(result):
            if not isinstance(item, dict):
                continue

            task = item.get("task") if isinstance(item.get("task"), dict) else item
            title = self._first_string(task, ["title", "name", "summary"])
            if not title:
                continue

            normalized.append(
                {
                    "id": self._first_string(task, ["id", "_id", "uuid"]) or title,
                    "title": title,
                    "status": self._first_string(task, ["status"]),
                    "priority": self._first_string(task, ["priority"]),
                    "start": self._first_string(item, self.SCHEDULED_START_KEYS)
                    or self._first_string(task, self.SCHEDULED_START_KEYS),
                    "deadline": self._first_string(task, ["deadline", "due_date", "dueDate"]),
                    "duration": self._first_int(task, ["duration", "duration_minutes", "durationMinutes"]),
                    "source": "akiflow",
                }
            )

        return normalized

    def _normalize_operator_tasks(self, result: Any) -> list[OperatorTask]:
        synced_at = datetime.now().replace(microsecond=0)
        normalized: list[OperatorTask] = []
        for item in self._extract_items(result):
            if not isinstance(item, dict):
                continue

            task = item.get("task") if isinstance(item.get("task"), dict) else item
            task_id = self._first_string(task, ["id", "_id", "uuid"])
            title = self._first_string(task, ["title", "name", "summary"])
            if not task_id or not title:
                continue

            scheduled_start = (
                self._first_string(item, self.SCHEDULED_START_KEYS)
                or self._first_string(task, self.SCHEDULED_START_KEYS)
            )
            project = task.get("project") if isinstance(task.get("project"), dict) else {}

            normalized.append(
                OperatorTask(
                    task_id=task_id,
                    title=title,
                    description=self._first_string(task, ["description", "notes", "body"]),
                    project_id=self._first_string(task, ["project_id", "projectId"])
                    or self._first_string(project, ["id", "_id", "uuid"]),
                    project_name=self._first_string(task, ["project_name", "projectName"])
                    or self._first_string(project, ["name", "title"]),
                    duration=self._first_int(task, ["duration", "duration_minutes", "durationMinutes"]),
                    priority=self._first_string(task, ["priority"]),
                    tags=self._first_string_list(task, ["tags", "labels"]),
                    links=self._first_string_list(task, ["links", "urls"]),
                    status=self._first_string(task, ["status"]),
                    scheduled_start=scheduled_start,
                    scheduled_date=self._date_part(scheduled_start),
                    deadline=self._first_string(task, ["deadline", "due_date", "dueDate"]),
                    done=self._first_bool(task, ["done", "completed", "is_completed", "isCompleted"]),
                    last_synced_at=synced_at,
                )
            )

        return normalized

    def _normalize_schedule(self, result: Any) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in self._extract_items(result):
            if not isinstance(item, dict):
                continue

            event = item.get("event") if isinstance(item.get("event"), dict) else item
            title = self._first_string(event, ["title", "name", "summary"])
            start = self._first_string(item, ["start", "start_datetime", "startDatetime", "datetime", "date"])
            start = start or self._first_string(event, ["start", "start_datetime", "startDatetime", "datetime", "date"])
            end = self._first_string(item, ["end", "end_datetime", "endDatetime"])
            end = end or self._first_string(event, ["end", "end_datetime", "endDatetime"])
            if not title or not start:
                continue

            normalized.append(
                {
                    "id": self._first_string(event, ["id", "_id", "uuid"]),
                    "title": title,
                    "start": start,
                    "end": end,
                    "duration": self._first_int(event, ["duration", "duration_minutes", "durationMinutes"]),
                    "kind": self._first_string(event, ["kind", "type"]) or "event",
                    "source": "akiflow",
                }
            )

        return normalized

    def _extract_items(self, value: Any) -> list[Any]:
        if isinstance(value, list):
            return value
        if not isinstance(value, dict):
            return []

        for key in ["tasks", "events", "items", "schedule", "structuredContent", "data", "result", "content"]:
            nested = value.get(key)
            if isinstance(nested, list):
                if key == "content":
                    return self._extract_text_items(nested)
                return nested
            if isinstance(nested, dict):
                extracted = self._extract_items(nested)
                if extracted:
                    return extracted

        return []

    def _extract_text_items(self, content: list[Any]) -> list[Any]:
        items: list[Any] = []
        for item in content:
            if not isinstance(item, dict) or item.get("type") != "text":
                continue

            text = item.get("text")
            if not isinstance(text, str):
                continue

            parsed = self._parse_json_from_text(text)
            if parsed is not None:
                items.extend(self._extract_items(parsed))

        return items

    def _parse_json_from_text(self, text: str) -> Any:
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            json_start = text.find("{")
            json_end = text.rfind("}")
            if json_start < 0 or json_end <= json_start:
                return None

        try:
            return json.loads(text[json_start : json_end + 1])
        except json.JSONDecodeError:
            return None

    def _first_string(self, item: dict[str, Any], keys: list[str]) -> str | None:
        for key in keys:
            value = item.get(key)
            if isinstance(value, str) and value:
                return value
        return None

    def _first_int(self, item: dict[str, Any], keys: list[str]) -> int | None:
        for key in keys:
            value = item.get(key)
            if isinstance(value, int):
                return value
            if isinstance(value, str) and value.isdigit():
                return int(value)
        return None

    def _first_bool(self, item: dict[str, Any], keys: list[str]) -> bool:
        for key in keys:
            value = item.get(key)
            if isinstance(value, bool):
                return value
        return False

    def _first_string_list(self, item: dict[str, Any], keys: list[str]) -> list[str]:
        for key in keys:
            value = item.get(key)
            if isinstance(value, list):
                return [str(entry) for entry in value if str(entry)]
        return []

    def _date_part(self, value: str | None) -> str | None:
        if not value:
            return None
        return value[:10]
