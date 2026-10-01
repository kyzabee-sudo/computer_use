# computer_use

A local Windows helper that lets an always-on agent see the desktop, read UI Automation, and click or type. It talks over stdin as an MCP server, or as one-shot commands. It does not open a network port, and it does nothing until you turn it on.

Cursor's built-in `--computer-use` worker drives macOS and Linux desktops. This package is the Windows path: run it on the signed-in Windows session you want the agent to use.

## What it can do

- List visible windows
- Capture the desktop or one window
- Read a bounded UI Automation tree and find controls by name
- Focus a window, click, type Unicode text, and press key chords
- Invoke a control or set its value when Windows exposes that pattern

Screenshots include `origin_x`, `origin_y`, and `scale`. A pixel in the image maps back to the screen with:

```text
screen_x = origin_x + image_x / scale
screen_y = origin_y + image_y / scale
```

Click coordinates are screen pixels.

## Install

On the Windows machine:

```powershell
py -3 -m pip install -e .
computer-use health
```

`health` works before you opt in. It reports whether control is enabled, whether the kill switch is present, and whether this process can see an interactive desktop.

## Turn it on

Either set an environment variable:

```powershell
$env:COMPUTER_USE_ENABLED = "1"
```

or create the enable file:

```powershell
New-Item -ItemType Directory -Force "$env:USERPROFILE\.computer-use"
New-Item -ItemType File "$env:USERPROFILE\.computer-use\enabled"
```

Limit which programs the agent can operate:

```powershell
$env:COMPUTER_USE_ALLOW_PROCESSES = "notepad.exe"
```

Stop a running helper immediately by creating the kill switch. Remove the file when you want control again.

```powershell
New-Item -ItemType File "$env:USERPROFILE\.computer-use\STOP"
```

Actions are appended to `%USERPROFILE%\.computer-use\audit.log`. Typed text is recorded as a character count, not the characters.

## Commands

```powershell
computer-use health
computer-use windows
computer-use screenshot --output desktop.png
computer-use tree --window 123456 --max-depth 3
computer-use find --window 123456 --name Save
computer-use focus --window 123456
computer-use click --window 123456
computer-use click --x 100 --y 200
computer-use type --window 123456 --text "hello"
computer-use key --window 123456 ctrl s
computer-use invoke --window 123456 --runtime-id 1,2,3
computer-use set-value --window 123456 --runtime-id 1,2,3 --value "hello"
```

`window` is the hwnd string or number from `windows`.

## MCP

After `pip install -e .`, point Cursor at the server. Leave `COMPUTER_USE_ENABLED` unset until you want the tools to succeed.

```json
{
  "mcpServers": {
    "computer-use": {
      "command": "computer-use",
      "args": ["mcp"],
      "env": {
        "COMPUTER_USE_ENABLED": "1",
        "COMPUTER_USE_ALLOW_PROCESSES": "notepad.exe"
      }
    }
  }
}
```

Grok Bot's local execution can run the same commands when Execution on Local Computer is allowed. Its own screen control stays on the cloud computer; this helper is what reaches the Windows desktop in front of you.

The server reads newline-delimited JSON-RPC from stdin and also accepts `Content-Length` frames. Logs go to stderr.

## Session requirements

Run it in the interactive session of the signed-in user. A Windows service runs in Session 0 and cannot see that desktop. Clicks and keystrokes also need the session unlocked.

Keep the helper and the target app at the same privilege level. An elevated helper cannot type into a normal window, and a normal helper cannot type into an elevated one.

UI Automation covers standard Win32, WPF, and WinUI controls. Games and custom-drawn canvases often have no control tree; use a screenshot and a click coordinate for those. Some apps hang while their accessibility tree is walked. Tree depth is capped at 8 and the walk stops after a few hundred nodes.

Per-monitor DPI awareness is requested so screenshot pixels and click points stay on the same grid.

## Development

The policy, coordinate mapping, key planner, CLI, and MCP framing are covered by unit tests and run on any platform. Desktop capture and input run on Windows.

```powershell
$env:PYTHONPATH = "src"
py -3 -m unittest discover -s tests
```
