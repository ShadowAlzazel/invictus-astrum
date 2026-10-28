"""A bench's log: what it prints goes to the screen and to logs/bench/NAME-YYYYmmdd-HHMMSS.txt,
headed by when it ran, on what commit (and whether with changes not committed), on what machine,
and with what settings (the battle tick, the warp)."""
import datetime
import platform
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class _Tee:
    def __init__(self, *outs):
        self.outs = outs

    def write(self, s):
        for o in self.outs:
            o.write(s)
        return len(s)

    def flush(self):
        for o in self.outs:
            o.flush()


def _git(*args) -> str:
    try:
        return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=10).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


def start(name: str, **said) -> Path:
    """Print from here on to the screen and to the bench's log too, under its heading; returns the log's path."""
    now = datetime.datetime.now().astimezone()
    path = ROOT / "logs" / "bench" / f"{name}-{now:%Y%m%d-%H%M%S}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    sys.stdout = _Tee(sys.__stdout__, open(path, "w", encoding="utf-8"))
    dirty = ", with changes not committed" if _git("status", "--porcelain", "--untracked-files=no") else ""
    print(f"{name}  {now:%Y-%m-%d %H:%M:%S %z}  {_git('rev-parse', '--abbrev-ref', 'HEAD')} {_git('log', '-1', '--format=%h %s')}{dirty}")
    print(f"  {platform.node()}, {platform.processor() or platform.machine()}, Python {platform.python_version()}"
          + "".join(f", {k.replace('_', ' ')} {v}" for k, v in said.items()))
    print(f"  log: {path.relative_to(ROOT)}\n")
    return path
