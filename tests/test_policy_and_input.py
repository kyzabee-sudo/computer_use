import ctypes
import json
import tempfile
import unittest
from pathlib import Path

from computer_use.coords import absolute_mouse, fit_size, image_to_screen
from computer_use.errors import PolicyError
from computer_use.keys import plan_chord, plan_text
from computer_use.policy import policy_from_env
from computer_use.service import ComputerUseService, _downscale
from computer_use.win32.input import INPUT, KEYBDINPUT, MOUSEINPUT
from tests.support import MIN_PNG, FakeDesktop


class CoordTests(unittest.TestCase):
    def test_fit_size_keeps_aspect(self):
        self.assertEqual(fit_size(300, 100, 256), (256, 85))
        self.assertEqual(fit_size(100, 50, 256), (100, 50))

    def test_image_point_maps_back_to_screen(self):
        self.assertEqual(image_to_screen(0, 0, -1920, 0, 0.5), (-1920, 0))
        self.assertEqual(image_to_screen(10, 20, 0, 0, 2), (5, 10))

    def test_absolute_mouse_uses_virtual_desktop_edges(self):
        self.assertEqual(absolute_mouse(0, 0, 0, 0, 1920, 1080), (0, 0))
        self.assertEqual(absolute_mouse(1919, 1079, 0, 0, 1920, 1080), (65535, 65535))


class KeyPlanTests(unittest.TestCase):
    def test_chord_presses_modifiers_around_the_key(self):
        events = plan_chord(["ctrl", "c"])
        self.assertEqual([(event.value, event.keyup) for event in events], [(0x11, False), (0x43, False), (0x43, True), (0x11, True)])

    def test_newline_becomes_enter_and_emoji_uses_surrogates(self):
        newline = plan_text("a\nb")
        self.assertEqual(newline[2].value, 0x0D)
        emoji = [event for event in plan_text("😀") if event.kind == "unicode" and not event.keyup]
        self.assertEqual(len(emoji), 2)


class StructTests(unittest.TestCase):
    def test_sendinput_struct_matches_64_bit_windows(self):
        if ctypes.sizeof(ctypes.c_void_p) != 8:
            self.skipTest("pointer size is not 8")
        self.assertEqual(ctypes.sizeof(MOUSEINPUT), 32)
        self.assertEqual(ctypes.sizeof(KEYBDINPUT), 24)
        self.assertEqual(ctypes.sizeof(INPUT), 40)

    def test_input_events_keep_coordinates(self):
        from computer_use.win32.input import INPUT_KEYBOARD, INPUT_MOUSE, _key, _mouse

        mouse = _mouse(10, 20, 1)
        self.assertEqual(mouse.type, INPUT_MOUSE)
        self.assertEqual((mouse.union.mi.dx, mouse.union.mi.dy), (10, 20))
        key = _key(0x41, 0, 0)
        self.assertEqual(key.type, INPUT_KEYBOARD)
        self.assertEqual(key.union.ki.wVk, 0x41)


class PolicyServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.desktop = FakeDesktop()

    def tearDown(self):
        self.tmp.cleanup()

    def service(self, **env):
        base = {"COMPUTER_USE_HOME": self.home, "COMPUTER_USE_ENABLED": "", "COMPUTER_USE_ALLOW_PROCESSES": ""}
        base.update(env)
        return ComputerUseService(self.desktop, base)

    def test_health_reports_disabled_without_touching_input(self):
        health = self.service().health()
        self.assertFalse(health["enabled"])
        self.assertFalse(health["kill_switch"])
        self.assertEqual(self.desktop.clicks, [])

    def test_enabled_file_turns_listing_on(self):
        Path(self.home, "enabled").write_text("on", encoding="utf-8")
        listed = self.service().list_windows()
        self.assertEqual([item["process"] for item in listed["windows"]], ["notepad.exe", "chrome.exe"])

    def test_disabled_blocks_and_writes_an_audit_line(self):
        with self.assertRaises(PolicyError):
            self.service().list_windows()
        audit = Path(self.home, "audit.log").read_text(encoding="utf-8")
        self.assertIn("disabled", audit)
        self.assertEqual(self.desktop.shots, [])

    def test_kill_switch_overrides_enablement(self):
        Path(self.home, "STOP").write_text("", encoding="utf-8")
        with self.assertRaises(PolicyError):
            self.service(COMPUTER_USE_ENABLED="1").screenshot()
        self.assertEqual(self.desktop.shots, [])

    def test_allowlist_filters_windows_and_blocks_other_processes(self):
        service = self.service(COMPUTER_USE_ENABLED="1", COMPUTER_USE_ALLOW_PROCESSES="notepad.exe")
        listed = service.list_windows()
        self.assertEqual([item["process"] for item in listed["windows"]], ["notepad.exe"])
        with self.assertRaises(PolicyError):
            service.screenshot()
        with self.assertRaises(PolicyError):
            service.click(250, 10, window_id=2)
        clicked = service.click(window_id=1)
        self.assertEqual(clicked["x"], 50)
        self.assertEqual(clicked["y"], 40)
        self.assertEqual(self.desktop.clicks, [(50, 40, "left", 1)])
        self.assertEqual(self.desktop.focused, [1])

    def test_invoke_and_set_value_target_the_allowed_window(self):
        service = self.service(COMPUTER_USE_ENABLED="1", COMPUTER_USE_ALLOW_PROCESSES="notepad.exe")
        service.invoke(1, [1, 2, 3])
        service.set_value(1, [1, 2, 3], "hi")
        self.assertEqual(self.desktop.invoked, (1, (1, 2, 3)))
        self.assertEqual(self.desktop.value, (1, (1, 2, 3), "hi"))

    def test_click_outside_the_window_does_not_land(self):
        service = self.service(COMPUTER_USE_ENABLED="1")
        with self.assertRaises(Exception) as caught:
            service.click(150, 10, window_id=1)
        self.assertIn("outside", str(caught.exception))
        self.assertEqual(self.desktop.clicks, [])

    def test_typing_is_audited_without_the_text(self):
        service = self.service(COMPUTER_USE_ENABLED="1")
        service.type_text("super-secret", window_id=1)
        audit = Path(self.home, "audit.log").read_text(encoding="utf-8")
        self.assertNotIn("super-secret", audit)
        self.assertIn('"chars":12', audit)
        self.assertEqual(self.desktop.focused, [1])
        self.assertTrue(self.desktop.keys)

    def test_locked_desktop_blocks_input_after_enablement(self):
        self.desktop.interactive = False
        service = self.service(COMPUTER_USE_ENABLED="1")
        with self.assertRaises(Exception) as caught:
            service.key(["enter"])
        self.assertIn("fake", str(caught.exception))
        self.assertEqual(self.desktop.keys, [])

    def test_downscale_reports_the_mapping_scale(self):
        try:
            from PIL import Image
        except ImportError:
            self.skipTest("Pillow is not installed")
        import io

        image = Image.new("RGB", (300, 100), "red")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        from computer_use.models import Shot

        shot = Shot(png=buffer.getvalue(), screen_width=300, screen_height=100, origin_x=-10, origin_y=5)
        png, width, height, scale = _downscale(shot, 256)
        self.assertEqual((width, height), (256, 85))
        self.assertAlmostEqual(scale, 256 / 300)
        self.assertNotEqual(png, MIN_PNG)
        mapped = image_to_screen(256, 85, shot.origin_x, shot.origin_y, scale)
        self.assertEqual((round(mapped[0]), round(mapped[1])), (290, 105))

    def test_policy_parses_allowlist(self):
        policy = policy_from_env({"COMPUTER_USE_HOME": self.home, "COMPUTER_USE_ALLOW_PROCESSES": "Notepad.exe, chrome.exe"})
        self.assertTrue(policy.allows_process("notepad.exe"))
        self.assertFalse(policy.allows_process("powershell.exe"))


class AuditJsonTests(unittest.TestCase):
    def test_audit_lines_are_json(self):
        with tempfile.TemporaryDirectory() as home:
            service = ComputerUseService(
                FakeDesktop(),
                {"COMPUTER_USE_HOME": home, "COMPUTER_USE_ENABLED": "1", "COMPUTER_USE_ALLOW_PROCESSES": ""},
            )
            service.list_windows()
            event = json.loads(Path(home, "audit.log").read_text(encoding="utf-8"))
            self.assertEqual(event["action"], "list_windows")
            self.assertIsNone(event["denied"])


if __name__ == "__main__":
    unittest.main()
