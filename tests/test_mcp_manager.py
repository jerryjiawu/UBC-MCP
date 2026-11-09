import atexit
import os
import tempfile
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


class SshConfigTests(unittest.TestCase):
    def setUp(self):
        self.client = mcp_manager.app.test_client()
        fd, self.env_path = tempfile.mkstemp(suffix=".env")
        os.close(fd)
        with open(self.env_path, "w") as fh:
            fh.write("OTHER=keep\n")
        self.patch = patch.object(mcp_manager, "ENV_PATH", self.env_path)
        self.patch.start()
        self.server = Mock()
        self.server.is_running.return_value = True
        self.managed = patch.dict(mcp_manager.managed, {"ssh-mcp": self.server})
        self.managed.start()

    def tearDown(self):
        self.managed.stop()
        self.patch.stop()
        os.remove(self.env_path)

    def test_save_and_read_never_returns_password(self):
        body = {"ssh_host": "h.example", "ssh_port": "2222",
                "ssh_username": "me", "ssh_password": "p'w\"d"}
        data = self.client.post("/api/ssh/config", json=body).json
        self.assertEqual(data, {"ssh_host": "h.example", "ssh_port": "2222",
                                "ssh_username": "me", "has_password": True})
        self.server.stop.assert_called_once()
        self.server.start.assert_called_once()
        env = mcp_manager.dotenv_values(self.env_path)
        self.assertEqual(env["SSH_PASSWORD"], "p'w\"d")
        self.assertEqual(env["OTHER"], "keep")
        # blank password keeps the saved one
        self.client.post("/api/ssh/config", json={**body, "ssh_password": ""})
        self.assertEqual(mcp_manager.dotenv_values(self.env_path)["SSH_PASSWORD"], "p'w\"d")

    def test_rejects_bad_input(self):
        self.assertEqual(self.client.post("/api/ssh/config", json={"ssh_port": "99999"}).status_code, 400)
        self.assertEqual(self.client.post("/api/ssh/config", json={"ssh_host": "a\nb"}).status_code, 400)
        self.server.start.assert_not_called()


if __name__ == "__main__":
    unittest.main()
