"""SQLite data layer for the church management app.

All database access goes through this module so the Streamlit UI never
writes SQL directly. Every function takes an open connection, which keeps
the functions easy to test against an in-memory database.
"""

import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

DEFAULT_DB_PATH = Path(__file__).parent / "data" / "church.db"

MEMBER_STATUSES = ["Member", "Regular attendee", "Visitor", "Inactive"]
GIVING_FUNDS = ["Tithe", "Offering", "Building fund", "Missions", "Welfare", "Other"]
PAYMENT_METHODS = ["Cash", "Mobile money", "Bank transfer", "Card", "Cheque"]
SERVICE_TYPES = ["Sunday service", "Midweek service", "Prayer meeting", "Youth service", "Special event"]

SCHEMA = """
CREATE TABLE IF NOT EXISTS members (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    first_name   TEXT NOT NULL,
    last_name    TEXT NOT NULL,
    gender       TEXT,
    phone        TEXT,
    email        TEXT,
    address      TEXT,
    birth_date   TEXT,
    join_date    TEXT,
    status       TEXT NOT NULL DEFAULT 'Member',
    ministry     TEXT,
    notes        TEXT,
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS services (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    service_date  TEXT NOT NULL,
    service_type  TEXT NOT NULL,
    headcount     INTEGER NOT NULL DEFAULT 0,
    notes         TEXT,
    UNIQUE (service_date, service_type)
);

CREATE TABLE IF NOT EXISTS attendance (
    service_id  INTEGER NOT NULL REFERENCES services(id) ON DELETE CASCADE,
    member_id   INTEGER NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    PRIMARY KEY (service_id, member_id)
);

CREATE TABLE IF NOT EXISTS donations (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    member_id     INTEGER REFERENCES members(id) ON DELETE SET NULL,
    donation_date TEXT NOT NULL,
    amount        REAL NOT NULL CHECK (amount > 0),
    fund          TEXT NOT NULL,
    method        TEXT,
    notes         TEXT
);

CREATE TABLE IF NOT EXISTS events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    event_date  TEXT NOT NULL,
    start_time  TEXT,
    location    TEXT,
    description TEXT
);
"""


def connect(path=DEFAULT_DB_PATH):
    """Open a connection and make sure the schema exists."""
    if str(path) != ":memory:":
        Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def _iso(value):
    """Store dates as ISO strings so SQLite sorts and filters them correctly."""
    if value is None or value == "":
        return None
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


# ---------------------------------------------------------------- members

MEMBER_FIELDS = [
    "first_name", "last_name", "gender", "phone", "email", "address",
    "birth_date", "join_date", "status", "ministry", "notes",
]


def add_member(conn, **fields):
    if not fields.get("first_name", "").strip() or not fields.get("last_name", "").strip():
        raise ValueError("First and last name are required.")
    values = {k: _iso(fields.get(k)) if k.endswith("_date") else fields.get(k) for k in MEMBER_FIELDS}
    values["status"] = values["status"] or "Member"
    cur = conn.execute(
        f"INSERT INTO members ({', '.join(MEMBER_FIELDS)}) "
        f"VALUES ({', '.join('?' for _ in MEMBER_FIELDS)})",
        [values[k] for k in MEMBER_FIELDS],
    )
    conn.commit()
    return cur.lastrowid


def update_member(conn, member_id, **fields):
    updates = {k: (_iso(v) if k.endswith("_date") else v) for k, v in fields.items() if k in MEMBER_FIELDS}
    if not updates:
        return
    assignments = ", ".join(f"{k} = ?" for k in updates)
    conn.execute(f"UPDATE members SET {assignments} WHERE id = ?", [*updates.values(), member_id])
    conn.commit()


def delete_member(conn, member_id):
    conn.execute("DELETE FROM members WHERE id = ?", (member_id,))
    conn.commit()


def list_members(conn, search="", status=None):
    sql = "SELECT * FROM members WHERE 1=1"
    params = []
    if search:
        sql += " AND (first_name || ' ' || last_name LIKE ? OR phone LIKE ? OR email LIKE ?)"
        like = f"%{search}%"
        params += [like, like, like]
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY last_name, first_name"
    return pd.read_sql_query(sql, conn, params=params)


def get_member(conn, member_id):
    row = conn.execute("SELECT * FROM members WHERE id = ?", (member_id,)).fetchone()
    return dict(row) if row else None


def upcoming_birthdays(conn, today, days=30):
    """Members whose birthday falls within the next `days` days (year ignored)."""
    members = list_members(conn)
    members = members[members["birth_date"].notna() & (members["birth_date"] != "")]
    rows = []
    for _, m in members.iterrows():
        try:
            born = date.fromisoformat(m["birth_date"])
        except ValueError:
            continue
        for year in (today.year, today.year + 1):
            try:
                nxt = born.replace(year=year)
            except ValueError:  # 29 February in a non-leap year
                nxt = date(year, 3, 1)
            if nxt >= today:
                break
        delta = (nxt - today).days
        if delta <= days:
            rows.append({"name": f"{m['first_name']} {m['last_name']}", "birthday": nxt, "in_days": delta, "phone": m["phone"]})
    return pd.DataFrame(rows, columns=["name", "birthday", "in_days", "phone"]).sort_values("in_days")


# ------------------------------------------------------------- attendance

def record_service(conn, service_date, service_type, headcount=0, notes="", member_ids=()):
    """Create or update a service and replace its list of checked-in members.

    The stored headcount is never lower than the number of members checked in,
    since visitors and children are often counted but not named.
    """
    member_ids = list(dict.fromkeys(member_ids))
    headcount = max(int(headcount or 0), len(member_ids))
    conn.execute(
        "INSERT INTO services (service_date, service_type, headcount, notes) VALUES (?, ?, ?, ?) "
        "ON CONFLICT (service_date, service_type) DO UPDATE SET headcount = excluded.headcount, notes = excluded.notes",
        (_iso(service_date), service_type, headcount, notes),
    )
    service_id = conn.execute(
        "SELECT id FROM services WHERE service_date = ? AND service_type = ?",
        (_iso(service_date), service_type),
    ).fetchone()["id"]
    conn.execute("DELETE FROM attendance WHERE service_id = ?", (service_id,))
    conn.executemany(
        "INSERT INTO attendance (service_id, member_id) VALUES (?, ?)",
        [(service_id, mid) for mid in member_ids],
    )
    conn.commit()
    return service_id


def get_service(conn, service_date, service_type):
    row = conn.execute(
        "SELECT * FROM services WHERE service_date = ? AND service_type = ?",
        (_iso(service_date), service_type),
    ).fetchone()
    if not row:
        return None
    service = dict(row)
    service["member_ids"] = [
        r["member_id"] for r in conn.execute("SELECT member_id FROM attendance WHERE service_id = ?", (service["id"],))
    ]
    return service


def list_services(conn, start=None, end=None):
    sql = """
        SELECT s.id, s.service_date, s.service_type, s.headcount,
               COUNT(a.member_id) AS members_checked_in, s.notes
        FROM services s LEFT JOIN attendance a ON a.service_id = s.id
        WHERE 1=1
    """
    params = []
    if start:
        sql += " AND s.service_date >= ?"
        params.append(_iso(start))
    if end:
        sql += " AND s.service_date <= ?"
        params.append(_iso(end))
    sql += " GROUP BY s.id ORDER BY s.service_date DESC, s.service_type"
    return pd.read_sql_query(sql, conn, params=params)


def absent_members(conn, since, min_services=3):
    """Active members who missed every one of the last services since `since`.

    Only counts once at least `min_services` services with check-ins exist in
    the window; otherwise there is not enough data to call anyone absent.
    """
    tracked = conn.execute(
        "SELECT COUNT(DISTINCT s.id) FROM services s JOIN attendance a ON a.service_id = s.id WHERE s.service_date >= ?",
        (_iso(since),),
    ).fetchone()[0]
    if tracked < min_services:
        return pd.DataFrame(columns=["id", "first_name", "last_name", "phone", "last_seen"])
    return pd.read_sql_query(
        """
        SELECT m.id, m.first_name, m.last_name, m.phone,
               (SELECT MAX(s.service_date) FROM attendance a JOIN services s ON s.id = a.service_id
                WHERE a.member_id = m.id) AS last_seen
        FROM members m
        WHERE m.status IN ('Member', 'Regular attendee')
          AND NOT EXISTS (
              SELECT 1 FROM attendance a JOIN services s ON s.id = a.service_id
              WHERE a.member_id = m.id AND s.service_date >= ?)
        ORDER BY last_seen IS NULL, last_seen, m.last_name
        """,
        conn,
        params=[_iso(since)],
    )


# ---------------------------------------------------------------- giving

def add_donation(conn, donation_date, amount, fund, member_id=None, method=None, notes=""):
    if amount is None or float(amount) <= 0:
        raise ValueError("Amount must be greater than zero.")
    cur = conn.execute(
        "INSERT INTO donations (member_id, donation_date, amount, fund, method, notes) VALUES (?, ?, ?, ?, ?, ?)",
        (member_id, _iso(donation_date), float(amount), fund, method, notes),
    )
    conn.commit()
    return cur.lastrowid


def delete_donation(conn, donation_id):
    conn.execute("DELETE FROM donations WHERE id = ?", (donation_id,))
    conn.commit()


def list_donations(conn, start=None, end=None, member_id=None):
    sql = """
        SELECT d.id, d.donation_date, d.amount, d.fund, d.method,
               COALESCE(m.first_name || ' ' || m.last_name, 'Anonymous') AS giver,
               d.member_id, d.notes
        FROM donations d LEFT JOIN members m ON m.id = d.member_id
        WHERE 1=1
    """
    params = []
    if start:
        sql += " AND d.donation_date >= ?"
        params.append(_iso(start))
    if end:
        sql += " AND d.donation_date <= ?"
        params.append(_iso(end))
    if member_id:
        sql += " AND d.member_id = ?"
        params.append(member_id)
    sql += " ORDER BY d.donation_date DESC, d.id DESC"
    return pd.read_sql_query(sql, conn, params=params)


# ---------------------------------------------------------------- events

def add_event(conn, title, event_date, start_time="", location="", description=""):
    if not title.strip():
        raise ValueError("Event title is required.")
    cur = conn.execute(
        "INSERT INTO events (title, event_date, start_time, location, description) VALUES (?, ?, ?, ?, ?)",
        (title.strip(), _iso(event_date), start_time, location, description),
    )
    conn.commit()
    return cur.lastrowid


def delete_event(conn, event_id):
    conn.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()


def list_events(conn, start=None):
    sql = "SELECT * FROM events"
    params = []
    if start:
        sql += " WHERE event_date >= ?"
        params.append(_iso(start))
    sql += " ORDER BY event_date, start_time"
    return pd.read_sql_query(sql, conn, params=params)
