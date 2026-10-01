#!/usr/bin/env python3
"""anon <netid|xHHHHH>

Map a netid to a stable anonymous ID of the form x + 5 hex digits, stored in a
SQLite DB. Port of the Haskell `anon`; produces identical IDs and shares its DB.

Env:
  ANON_DB    path to DB (default ~/.local/share/anon/anon.db)
  ANON_SALT  course-specific salt (default "change-me-course-salt")
"""

import hashlib
import os
import sqlite3
import string
import sys
from itertools import count
from pathlib import Path

MASK20 = 0xFFFFF


def db_path() -> Path:
    env = os.environ.get("ANON_DB")
    if env is not None:
        return Path(env)
    return Path.home() / ".local" / "share" / "anon" / "anon.db"


def salt() -> str:
    return os.environ.get("ANON_SALT", "change-me-course-salt")


def init_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS anon_map ("
        "  netid TEXT PRIMARY KEY,"
        "  anon  TEXT UNIQUE NOT NULL"
        ")"
    )
    conn.commit()


def is_anon_token(s: str) -> bool:
    return len(s) == 6 and s[0] == "x" and all(c in string.hexdigits for c in s[1:])


def lookup_by_netid(conn, netid):
    row = conn.execute("SELECT anon FROM anon_map WHERE netid = ?", (netid,)).fetchone()
    return row[0] if row else None


def lookup_by_anon(conn, anon):
    row = conn.execute("SELECT netid FROM anon_map WHERE anon = ?", (anon,)).fetchone()
    return row[0] if row else None


# --- Hashing / ID generation -------------------------------------------------
# x + 5 hex digits = 20 bits. h1 from salt+netid, h2 from (h1, salt, netid),
# mixed together; on collision, probe with a counter.

def _sha_int(s: str) -> int:
    # Haskell packed each Char via fromEnum, truncating to its low byte.
    data = bytes(ord(c) & 0xFF for c in s)
    return int.from_bytes(hashlib.sha256(data).digest()[:4], "big")


def _rotl20(x: int, k: int) -> int:
    m = x & MASK20
    k %= 20
    return ((m << k) | (m >> (20 - k))) & MASK20


def anon_id_from(salt: str, netid: str, counter: int) -> str:
    h1 = _sha_int(f"{salt}|v1|{netid}|{counter}")
    h2 = _sha_int(f"{salt}|v2|{h1 & MASK20}|{netid}|{counter}")
    mixed = (h1 & MASK20) ^ _rotl20(h2 & MASK20, 7)
    return f"x{mixed:05x}"


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: anon <netid|xHHHHH>")
    inp = sys.argv[1]

    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    s = salt()

    conn = sqlite3.connect(path)
    try:
        init_schema(conn)
        if is_anon_token(inp):
            a = inp.lower()
            if lookup_by_anon(conn, a) is None:
                sys.exit(f"anon: not found: {a}")
            print(a)
        else:
            a = lookup_by_netid(conn, inp)
            if a is None:
                a = next(c for c in (anon_id_from(s, inp, i) for i in count())
                         if lookup_by_anon(conn, c) is None)
                conn.execute("INSERT INTO anon_map(netid, anon) VALUES(?, ?)", (inp, a))
                conn.commit()
            print(a)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
