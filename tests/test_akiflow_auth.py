from __future__ import annotations

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from productivity_operator.services.akiflow_service import AkiflowService


class AkiflowAuthTests(unittest.TestCase):
    def test_loads_cached_token_on_startup(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            token_path = Path(temp_dir) / "token.json"
            token_path.write_text(
                json.dumps(
                    {
                        "access_token": "access-token",
                        "refresh_token": "refresh-token",
                        "expires_at": time.time() + 3600,
                        "client_id": "client-id",
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(
                "os.environ",
                {
                    "AKIFLOW_TOKEN_CACHE_PATH": str(token_path),
                    "AKIFLOW_MCP_BEARER_TOKEN": "",
                    "AKIFLOW_OAUTH_CLIENT_ID": "",
                },
                clear=False,
            ):
                service = AkiflowService()

            self.assertEqual(service.bearer_token, "access-token")
            self.assertEqual(service.refresh_token, "refresh-token")
            self.assertEqual(service.client_id, "client-id")
            self.assertTrue(service.auth_status()["connected"])

    def test_expired_cached_token_without_refresh_requires_login(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            token_path = Path(temp_dir) / "token.json"
            token_path.write_text(
                json.dumps(
                    {
                        "access_token": "access-token",
                        "expires_at": time.time() - 3600,
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(
                "os.environ",
                {
                    "AKIFLOW_TOKEN_CACHE_PATH": str(token_path),
                    "AKIFLOW_MCP_BEARER_TOKEN": "",
                    "AKIFLOW_OAUTH_CLIENT_ID": "",
                },
                clear=False,
            ):
                service = AkiflowService()

            status = service.auth_status()
            self.assertFalse(status["connected"])
            self.assertIn("expired", status["message"])

    def test_normalizes_start_time_as_scheduled_start(self) -> None:
        service = AkiflowService()

        tasks = service._normalize_operator_tasks(
            {
                "tasks": [
                    {
                        "id": "task-1",
                        "title": "Scheduled task",
                        "startTime": "2026-06-30T09:00:00",
                        "duration": 30,
                    }
                ]
            }
        )

        self.assertEqual(tasks[0].scheduled_start, "2026-06-30T09:00:00")
        self.assertEqual(tasks[0].scheduled_date, "2026-06-30")


if __name__ == "__main__":
    unittest.main()
