"""Who may sign in, and who is signed in. The web process's alone: the simulation never knows a
user, only the side and level a request is made for (astrum/lobby.py says which).

The users are a document (data/users.toml): a name and its password's hash, nothing else. A
session is a random token in a cookie, kept in the web process's memory: the server started
again, everyone signs in again. Basic on purpose, for a local network:

    python -m astrum.accounts NAME PASSWORD      # a [[user]] entry for data/users.toml
"""
from __future__ import annotations

import hashlib
import hmac
import secrets
import sys
import threading
import tomllib
from pathlib import Path

ROUNDS = 100_000
COOKIE = "astrum_session"


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(8)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), ROUNDS).hex()
    return f"pbkdf2_sha256${ROUNDS}${salt}${digest}"


def matches(password: str, stored: str) -> bool:
    try:
        kind, rounds, salt, digest = stored.split("$")
    except ValueError:
        return False
    got = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(rounds)).hex()
    return kind == "pbkdf2_sha256" and hmac.compare_digest(got, digest)


def load_users(path: str | Path) -> dict[str, str]:
    """name -> its password's hash. Names are matched without case; shown as written."""
    path = Path(path)
    if not path.exists():
        return {}
    with path.open("rb") as f:
        doc = tomllib.load(f)
    return {u["name"]: u["password"] for u in doc.get("user", []) if u.get("name") and u.get("password")}


class Accounts:
    def __init__(self, path: str | Path):
        self.path = path
        self._sessions: dict[str, str] = {}               # token -> user
        self._lock = threading.Lock()

    def sign_in(self, name: str, password: str) -> tuple[str, str] | None:
        """(user as written, a new session's token), or None."""
        users = load_users(self.path)                     # (read each time: added users count at once)
        user = next((u for u in users if u.lower() == (name or "").strip().lower()), None)
        if user is None or not matches(password or "", users[user]):
            return None
        token = secrets.token_urlsafe(24)
        with self._lock:
            self._sessions[token] = user
        return user, token

    def who(self, token: str | None) -> str | None:
        return self._sessions.get(token or "")

    def sign_out(self, token: str | None) -> None:
        with self._lock:
            self._sessions.pop(token or "", None)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("python -m astrum.accounts NAME PASSWORD")
    print(f'[[user]]\nname = "{sys.argv[1]}"\npassword = "{hash_password(sys.argv[2])}"')
