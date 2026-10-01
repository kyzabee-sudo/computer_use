import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from computer_use.cli import main
from computer_use.errors import ComputerUseError
from computer_use.mcp_server import handle, read_message, serve, tool_specs
from computer_use.service import ComputerUseService
from computer_use.win32 import desktop
from tests.support import FakeDesktop


def _env(home: str, enabled: str = "") -> dict[str, str]:
    return {"COMPUTER_USE_HOME": home, "COMPUTER_USE_ENABLED": enabled, "COMPUTER_USE_ALLOW_PROCESSES": ""}


def _serve(service, messages):
    raw = b"".join(json.dumps(message).encode("utf-8") + b"\n" for message in messages)
    writer = io.BytesIO()
    serve(service, io.BytesIO(raw), writer)
    return [json.loads(line) for line in writer.getvalue().splitlines() if line.strip()]


class McpTests(unittest.TestCase):
    def test_initialize_lists_tools_and_returns_a_screenshot(self):
        with tempfile.TemporaryDirectory() as home:
            service = ComputerUseService(FakeDesktop(), _env(home, "1"))
            replies = _serve(
                service,
                [
                    {
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "initialize",
                        "params": {"protocolVersion": "2024-11-05", "capabilities": {}},
                    },
                    {"jsonrpc": "2.0", "method": "notifications/initialized"},
                    {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                    {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "screenshot", "arguments": {}}},
                ],
            )
        self.assertEqual([reply["id"] for reply in replies], [1, 2, 3])
        names = [tool["name"] for tool in replies[1]["result"]["tools"]]
        self.assertIn("click", names)
        self.assertEqual(len(names), len(tool_specs()))
        content = replies[2]["result"]["content"]
        self.assertEqual(content[1]["mimeType"], "image/png")
        meta = json.loads(content[0]["text"])
        self.assertEqual(meta["scale"], 1.0)
        self.assertIn("screen_x", meta["map"])

    def test_disabled_click_is_a_tool_error(self):
        with tempfile.TemporaryDirectory() as home:
            service = ComputerUseService(FakeDesktop(), _env(home))
            reply = handle(
                service,
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {"name": "click", "arguments": {"x": 1, "y": 2}},
                },
            )
        self.assertTrue(reply["result"]["isError"])
        self.assertIn("disabled", reply["result"]["content"][0]["text"])

    def test_content_length_frames_are_accepted(self):
        body = json.dumps({"jsonrpc": "2.0", "id": 7, "method": "ping"}).encode("utf-8")
        frame = b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body
        self.assertEqual(read_message(io.BytesIO(frame))["method"], "ping")

    def test_unknown_frame_is_rejected(self):
        with self.assertRaises(ComputerUseError):
            read_message(io.BytesIO(b"GET / HTTP/1.1\r\n"))


class CliTests(unittest.TestCase):
    def test_health_on_this_machine_stays_disabled(self):
        with tempfile.TemporaryDirectory() as home:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(["health"], _env(home))
        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertFalse(payload["enabled"])
        self.assertFalse(payload["desktop"]["interactive"])

    def test_windows_command_reports_the_policy_block(self):
        with tempfile.TemporaryDirectory() as home:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(["windows"], _env(home))
        self.assertEqual(code, 2)
        self.assertIn("disabled", stdout.getvalue())

    def test_enabled_windows_command_explains_the_platform(self):
        with tempfile.TemporaryDirectory() as home:
            stdout = io.StringIO()
            with redirect_stdout(stdout):
                code = main(["windows"], _env(home, "1"))
        self.assertEqual(code, 1)
        self.assertIn("Windows", stdout.getvalue())


class WindowsModuleTests(unittest.TestCase):
    def test_desktop_helpers_refuse_to_run_off_windows(self):
        if __import__("sys").platform == "win32":
            self.skipTest("this check covers the non-Windows process")
        with self.assertRaises(ComputerUseError):
            desktop.list_windows()


if __name__ == "__main__":
    unittest.main()
