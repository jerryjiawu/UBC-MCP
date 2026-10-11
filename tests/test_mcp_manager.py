import atexit
import unittest
from unittest.mock import Mock, patch

import mcp_manager

# Importing the supervisor must not clean up a running manager's PID files.
atexit.unregister(mcp_manager._stop_all)


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.client = mcp_manager.app.test_client()

    def test_dashboard_template(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        for marker in (
            'name="viewport"',
            'id="servers"',
            'id="server-template"',
            'id="brief"',
            'id="reference"',
            'id="status-error"',
            'id="brief-error"',
            "grid-template-columns: minmax(0, 1fr)",
            "setInterval(refresh, 2000)",
            "setInterval(refreshBrief, 30000)",
        ):
            self.assertIn(marker, html)

    def test_status_preserves_process_and_log_fields(self):
        status = {
            "name": "example", "running": True, "pid": 123,
            "uptime": 90, "logs": ["<script>not markup</script>"],
        }
        server = Mock()
        server.status.return_value = status
        with patch.dict(mcp_manager.managed, {"example": server}, clear=True):
            self.assertEqual(self.client.get("/api/status").json, {"example": status})

    def test_controls_use_existing_server_actions(self):
        server = Mock()
        server.status.return_value = {"running": True}
        with patch.dict(mcp_manager.managed, {"example": server}, clear=True):
            for action, expected in (
                ("start", ["start", "status"]),
                ("stop", ["stop", "status"]),
                ("restart", ["stop", "start", "status"]),
            ):
                with self.subTest(action=action):
                    server.reset_mock()
                    response = self.client.post(f"/api/example/{action}")
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual([call[0] for call in server.mock_calls], expected)
            for action in ("start", "stop", "restart"):
                self.assertEqual(self.client.post(f"/api/unknown/{action}").status_code, 404)

    def test_missing_brief_is_explicit(self):
        with patch("builtins.open", side_effect=FileNotFoundError):
            brief = self.client.get("/api/brief").json
        self.assertFalse(brief["exists"])
        self.assertIn("no brief yet", brief["text"])


if __name__ == "__main__":
    unittest.main()
