"""Opt-in gate. The helper stays inert until this policy says otherwise."""

from dataclasses import dataclass
import os
from pathlib import Path


_TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Policy:
    enabled: bool
    home: Path
    allow_processes: frozenset[str]

    def kill_switch_active(self) -> bool:
        return (self.home / "STOP").exists()

    def allows_process(self, process: str | None) -> bool:
        if not self.allow_processes:
            return True
        if not process:
            return False
        return process.lower() in self.allow_processes


def policy_from_env(env: dict[str, str] | None = None) -> Policy:
    """Read enablement, the kill-switch directory, and the process allowlist.

    Enablement is checked on every action, so creating the ``enabled`` file or
    the ``STOP`` file takes effect without restarting the helper.
    """
    values = os.environ if env is None else env
    home = Path(values.get("COMPUTER_USE_HOME", str(Path.home() / ".computer-use")))
    flag = values.get("COMPUTER_USE_ENABLED", "").strip().lower()
    enabled = flag in _TRUE or (home / "enabled").is_file()
    raw_allow = values.get("COMPUTER_USE_ALLOW_PROCESSES", "")
    allow = frozenset(part.strip().lower() for part in raw_allow.split(",") if part.strip())
    return Policy(enabled=enabled, home=home, allow_processes=allow)
