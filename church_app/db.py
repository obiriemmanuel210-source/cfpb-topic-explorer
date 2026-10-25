"""Data layer for the church management app.

All database access goes through this module so the Streamlit UI never
writes SQL directly. It runs on SQLite (a local file, the default) or on
Postgres (e.g. Supabase) when given a postgresql:// URL, using SQL that
works on both. Every function takes an engine, which keeps them easy to
test against an in-memory database.
"""

import csv
import io
import math
import secrets
import zipfile
from datetime import date, datetime
from pathlib import Path

import pandas as pd
from sqlalchemy import (
    CheckConstraint, Column, Float, ForeignKey, Integer, MetaData, String, Table, Text,
    UniqueConstraint, create_engine, event, func, inspect, select, text,
)
from sqlalchemy.pool import StaticPool

DEFAULT_DB_PATH = Path(__file__).parent / "data" / "church.db"

MEMBER_STATUSES = ["Member", "Regular attendee", "Visitor", "Inactive"]
GIVING_FUNDS = ["Tithe", "Offering", "Building fund", "Missions", "Welfare", "Other"]
PAYMENT_METHODS = ["Cash", "Mobile money", "Bank transfer", "Card", "Cheque"]
SERVICE_TYPES = ["Sunday service", "Midweek service", "Prayer meeting", "Youth service", "Special event"]
GROUP_KINDS = ["Cell / home group", "Ministry", "Department", "Class", "Other"]
CHILDREN_CLASSES = ["Nursery (0-2)", "Beginners (3-5)", "Primary (6-9)", "Juniors (10-12)"]

metadata = MetaData()

users = Table(
    "users", metadata,
    Column("id", Integer, primary_key=True),
    Column("username", String(80), nullable=False, unique=True),
    Column("full_name", String(200)),
    Column("password_hash", String(300), nullable=False),
    Column("role", String(30), nullable=False),
    Column("active", Integer, nullable=False, server_default="1"),
    Column("created_at", String(30)),
)

members = Table(
    "members", metadata,
    Column("id", Integer, primary_key=True),
    Column("first_name", String(100), nullable=False),
    Column("last_name", String(100), nullable=False),
    Column("gender", String(20)),
    Column("phone", String(40)),
    Column("email", String(200)),
    Column("address", Text),
    Column("birth_date", String(10)),
    Column("join_date", String(10)),
    Column("status", String(30), nullable=False, server_default="Member"),
    Column("ministry", String(200)),
    Column("notes", Text),
    Column("created_at", String(30)),
)

groups = Table(
    "church_groups", metadata,
    Column("id", Integer, primary_key=True),
    Column("name", String(150), nullable=False, unique=True),
    Column("kind", String(50)),
    Column("leader_id", Integer, ForeignKey("members.id", ondelete="SET NULL")),
    Column("meeting_time", String(100)),
    Column("notes", Text),
)

group_members = Table(
    "group_members", metadata,
    Column("group_id", Integer, ForeignKey("church_groups.id", ondelete="CASCADE"), primary_key=True),
    Column("member_id", Integer, ForeignKey("members.id", ondelete="CASCADE"), primary_key=True),
)

services = Table(
    "services", metadata,
    Column("id", Integer, primary_key=True),
    Column("service_date", String(10), nullable=False),
    Column("service_type", String(50), nullable=False),
    Column("headcount", Integer, nullable=False, server_default="0"),
    Column("notes", Text),
    UniqueConstraint("service_date", "service_type"),
)

attendance = Table(
    "attendance", metadata,
    Column("service_id", Integer, ForeignKey("services.id", ondelete="CASCADE"), primary_key=True),
    Column("member_id", Integer, ForeignKey("members.id", ondelete="CASCADE"), primary_key=True),
)

donations = Table(
    "donations", metadata,
    Column("id", Integer, primary_key=True),
    Column("member_id", Integer, ForeignKey("members.id", ondelete="SET NULL")),
    Column("donation_date", String(10), nullable=False),
    Column("amount", Float, nullable=False),
    Column("fund", String(50), nullable=False),
    Column("method", String(50)),
    Column("notes", Text),
    Column("recorded_by", String(80)),
    CheckConstraint("amount > 0", name="amount_positive"),
)

pledges = Table(
    "pledges", metadata,
    Column("id", Integer, primary_key=True),
    Column("member_id", Integer, ForeignKey("members.id", ondelete="CASCADE"), nullable=False),
    Column("fund", String(50), nullable=False),
    Column("amount", Float, nullable=False),
    Column("start_date", String(10), nullable=False),
    Column("end_date", String(10), nullable=False),
    Column("notes", Text),
    CheckConstraint("amount > 0", name="pledge_amount_positive"),
)

events = Table(
    "events", metadata,
    Column("id", Integer, primary_key=True),
    Column("title", String(200), nullable=False),
    Column("event_date", String(10), nullable=False),
    Column("start_time", String(10)),
    Column("location", String(200)),
    Column("description", Text),
)

children = Table(
    "children", metadata,
    Column("id", Integer, primary_key=True),
    Column("first_name", String(100), nullable=False),
    Column("last_name", String(100), nullable=False),
    Column("birth_date", String(10)),
    Column("class_name", String(50)),
    Column("guardian_id", Integer, ForeignKey("members.id", ondelete="SET NULL")),
    Column("guardian_name", String(200)),
    Column("guardian_phone", String(40)),
    Column("medical_notes", Text),
)

child_checkins = Table(
    "child_checkins", metadata,
    Column("id", Integer, primary_key=True),
    Column("child_id", Integer, ForeignKey("children.id", ondelete="CASCADE"), nullable=False),
    Column("checkin_date", String(10), nullable=False),
    Column("class_name", String(50)),
    Column("security_code", String(10), nullable=False),
    Column("checked_in_at", String(30), nullable=False),
    Column("checked_in_by", String(80)),
    Column("checked_out_at", String(30)),
    Column("picked_up_by", String(200)),
    UniqueConstraint("child_id", "checkin_date"),
)

audit_log = Table(
    "audit_log", metadata,
    Column("id", Integer, primary_key=True),
    Column("at", String(30), nullable=False),
    Column("username", String(80)),
    Column("action", String(80), nullable=False),
    Column("details", Text),
)

# Order matters for backup/restore: parents before the tables that point at them.
BACKUP_TABLES = [members, groups, group_members, services, attendance, donations, pledges,
                 events, children, child_checkins, audit_log]


def connect(url=None):
    """Create an engine and make sure every table exists.

    `url` may be a SQLAlchemy URL (sqlite:///..., postgresql://...), a file
    path, ":memory:", or None for the default local SQLite file.
    """
    url = str(url or DEFAULT_DB_PATH)
    if url == ":memory:":
        engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    elif "://" not in url:
        Path(url).parent.mkdir(parents=True, exist_ok=True)
        engine = create_engine(f"sqlite:///{url}", connect_args={"check_same_thread": False})
    else:
        if url.startswith("postgres://"):  # the form many hosts hand out
            url = "postgresql://" + url[len("postgres://"):]
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://"):]
        engine = create_engine(url, pool_pre_ping=True)

    if engine.dialect.name == "sqlite":
        @event.listens_for(engine, "connect")
        def _fk_on(dbapi_conn, _):
            dbapi_conn.execute("PRAGMA foreign_keys = ON")

    metadata.create_all(engine)
    _add_missing_columns(engine)
    return engine


def _add_missing_columns(engine):
    """Bring a database made by an older version of the app up to date.

    create_all() only creates missing tables; it never changes existing
    ones. New optional columns are added here so old data keeps working.
    """
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in metadata.sorted_tables:
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for column in table.columns:
                if column.name not in existing and column.nullable:
                    col_type = column.type.compile(dialect=engine.dialect)
                    conn.execute(text(f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" {col_type}'))


def _iso(value):
    """Store dates as ISO strings so they sort and filter correctly on any database."""
    if value is None or value == "":
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    return str(value)


def _now():
    return datetime.now().isoformat(timespec="seconds")


def _df(engine, sql, **params):
    with engine.connect() as conn:
        return pd.read_sql_query(text(sql), conn, params=params)


def _insert(engine, table, **values):
    with engine.begin() as conn:
        return conn.execute(table.insert().values(**values)).inserted_primary_key[0]


def _delete(engine, table, row_id):
    with engine.begin() as conn:
        conn.execute(table.delete().where(table.c.id == row_id))


def _one(engine, table, row_id):
    with engine.connect() as conn:
        row = conn.execute(select(table).where(table.c.id == row_id)).mappings().first()
    return dict(row) if row else None


# ------------------------------------------------------------- audit log

def log(engine, username, action, details="", at=None):
    _insert(engine, audit_log, at=_iso(at) or _now(), username=username, action=action, details=details)


def list_audit(engine, limit=500):
    return _df(engine, "SELECT at, username, action, details FROM audit_log ORDER BY id DESC LIMIT :n", n=limit)


def count_actions(engine, action, username, since):
    """How many times `action` was logged for `username` since a time (used for login lockout)."""
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(audit_log).where(
            audit_log.c.action == action, audit_log.c.username == username, audit_log.c.at >= _iso(since))).scalar()


# ------------------------------------------------------------------ users

def count_users(engine):
    with engine.connect() as conn:
        return conn.execute(select(func.count()).select_from(users)).scalar()


def add_user(engine, username, password_hash, role, full_name=""):
    username = username.strip().lower()
    if not username:
        raise ValueError("Username is required.")
    with engine.connect() as conn:
        if conn.execute(select(users.c.id).where(users.c.username == username)).first():
            raise ValueError(f"Username '{username}' is already taken.")
    return _insert(engine, users, username=username, full_name=full_name, password_hash=password_hash,
                   role=role, active=1, created_at=_now())


def get_user(engine, user_id=None, username=None):
    with engine.connect() as conn:
        q = select(users)
        q = q.where(users.c.id == user_id) if user_id is not None else q.where(users.c.username == (username or "").strip().lower())
        row = conn.execute(q).mappings().first()
    return dict(row) if row else None


def update_user(engine, user_id, **fields):
    allowed = {k: v for k, v in fields.items() if k in ("full_name", "password_hash", "role", "active")}
    if allowed:
        with engine.begin() as conn:
            conn.execute(users.update().where(users.c.id == user_id).values(**allowed))


def list_users(engine):
    return _df(engine, "SELECT id, username, full_name, role, active, created_at FROM users ORDER BY username")


# ---------------------------------------------------------------- members

MEMBER_FIELDS = [
    "first_name", "last_name", "gender", "phone", "email", "address",
    "birth_date", "join_date", "status", "ministry", "notes",
]


def _member_values(fields):
    return {k: (_iso(v) if k.endswith("_date") else v) for k, v in fields.items() if k in MEMBER_FIELDS}


def add_member(engine, **fields):
    if not (fields.get("first_name") or "").strip() or not (fields.get("last_name") or "").strip():
        raise ValueError("First and last name are required.")
    values = _member_values(fields)
    values["status"] = values.get("status") or "Member"
    return _insert(engine, members, created_at=_now(), **values)


def update_member(engine, member_id, **fields):
    values = _member_values(fields)
    if values:
        with engine.begin() as conn:
            conn.execute(members.update().where(members.c.id == member_id).values(**values))


def delete_member(engine, member_id):
    _delete(engine, members, member_id)


def get_member(engine, member_id):
    return _one(engine, members, member_id)


def list_members(engine, search="", status=None):
    sql = "SELECT * FROM members WHERE 1=1"
    params = {}
    if search:
        sql += (" AND (LOWER(first_name || ' ' || last_name) LIKE :q"
                " OR LOWER(COALESCE(phone, '')) LIKE :q OR LOWER(COALESCE(email, '')) LIKE :q)")
        params["q"] = f"%{search.strip().lower()}%"
    if status:
        sql += " AND status = :status"
        params["status"] = status
    sql += " ORDER BY last_name, first_name"
    return _df(engine, sql, **params)


def upcoming_birthdays(engine, today, days=30):
    """Members whose birthday falls within the next `days` days (year ignored)."""
    people = list_members(engine)
    people = people[people["birth_date"].notna() & (people["birth_date"] != "")]
    rows = []
    for _, m in people.iterrows():
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
            rows.append({"id": m["id"], "name": f"{m['first_name']} {m['last_name']}", "first_name": m["first_name"],
                         "birthday": nxt, "in_days": delta, "phone": m["phone"]})
    return pd.DataFrame(rows, columns=["id", "name", "first_name", "birthday", "in_days", "phone"]).sort_values("in_days")


# ----------------------------------------------------------------- groups

def add_group(engine, name, kind=None, leader_id=None, meeting_time="", notes=""):
    name = (name or "").strip()
    if not name:
        raise ValueError("Group name is required.")
    with engine.connect() as conn:
        if conn.execute(select(groups.c.id).where(func.lower(groups.c.name) == name.lower())).first():
            raise ValueError(f"A group called '{name}' already exists.")
    return _insert(engine, groups, name=name, kind=kind, leader_id=leader_id, meeting_time=meeting_time, notes=notes)


def update_group(engine, group_id, **fields):
    values = {k: v for k, v in fields.items() if k in ("name", "kind", "leader_id", "meeting_time", "notes")}
    if values:
        with engine.begin() as conn:
            conn.execute(groups.update().where(groups.c.id == group_id).values(**values))


def delete_group(engine, group_id):
    _delete(engine, groups, group_id)


def get_group(engine, group_id):
    return _one(engine, groups, group_id)


def list_groups(engine):
    return _df(engine, """
        SELECT g.id, g.name, g.kind, g.meeting_time,
               COALESCE(l.first_name || ' ' || l.last_name, '') AS leader,
               (SELECT COUNT(*) FROM group_members gm WHERE gm.group_id = g.id) AS members,
               g.leader_id, g.notes
        FROM church_groups g LEFT JOIN members l ON l.id = g.leader_id
        ORDER BY g.name
    """)


def set_group_members(engine, group_id, member_ids):
    member_ids = list(dict.fromkeys(int(m) for m in member_ids))
    with engine.begin() as conn:
        conn.execute(group_members.delete().where(group_members.c.group_id == group_id))
        if member_ids:
            conn.execute(group_members.insert(), [{"group_id": group_id, "member_id": m} for m in member_ids])


def group_member_ids(engine, group_id):
    with engine.connect() as conn:
        return [r[0] for r in conn.execute(select(group_members.c.member_id).where(group_members.c.group_id == group_id))]


def list_group_members(engine, group_id):
    return _df(engine, """
        SELECT m.id, m.first_name, m.last_name, m.phone, m.email, m.status
        FROM group_members gm JOIN members m ON m.id = gm.member_id
        WHERE gm.group_id = :g ORDER BY m.last_name, m.first_name
    """, g=group_id)


def member_groups(engine, member_id):
    return _df(engine, """
        SELECT g.id, g.name, g.kind FROM group_members gm JOIN church_groups g ON g.id = gm.group_id
        WHERE gm.member_id = :m ORDER BY g.name
    """, m=member_id)


# ------------------------------------------------------------- attendance

def record_service(engine, service_date, service_type, headcount=0, notes="", member_ids=()):
    """Create or update a service and replace its list of checked-in members.

    The stored headcount is never lower than the number of members checked in,
    since visitors and children are often counted but not named.
    """
    member_ids = list(dict.fromkeys(int(m) for m in member_ids))
    headcount = max(int(headcount or 0), len(member_ids))
    params = {"d": _iso(service_date), "t": service_type, "h": headcount, "n": notes}
    with engine.begin() as conn:
        conn.execute(text(
            "INSERT INTO services (service_date, service_type, headcount, notes) VALUES (:d, :t, :h, :n) "
            "ON CONFLICT (service_date, service_type) DO UPDATE SET headcount = excluded.headcount, notes = excluded.notes"
        ), params)
        service_id = conn.execute(
            select(services.c.id).where(services.c.service_date == params["d"], services.c.service_type == service_type)
        ).scalar()
        conn.execute(attendance.delete().where(attendance.c.service_id == service_id))
        if member_ids:
            conn.execute(attendance.insert(), [{"service_id": service_id, "member_id": m} for m in member_ids])
    return service_id


def get_service(engine, service_date, service_type):
    with engine.connect() as conn:
        row = conn.execute(select(services).where(
            services.c.service_date == _iso(service_date), services.c.service_type == service_type)).mappings().first()
        if not row:
            return None
        service = dict(row)
        service["member_ids"] = [r[0] for r in conn.execute(
            select(attendance.c.member_id).where(attendance.c.service_id == service["id"]))]
    return service


def list_services(engine, start=None, end=None):
    sql = """
        SELECT s.id, s.service_date, s.service_type, s.headcount,
               COUNT(a.member_id) AS members_checked_in, s.notes
        FROM services s LEFT JOIN attendance a ON a.service_id = s.id
        WHERE 1=1
    """
    params = {}
    if start:
        sql += " AND s.service_date >= :start"
        params["start"] = _iso(start)
    if end:
        sql += " AND s.service_date <= :end"
        params["end"] = _iso(end)
    sql += " GROUP BY s.id, s.service_date, s.service_type, s.headcount, s.notes ORDER BY s.service_date DESC, s.service_type"
    return _df(engine, sql, **params)


def absent_members(engine, since, min_services=3):
    """Active members who missed every service since `since`.

    Only counts once at least `min_services` services with check-ins exist in
    the window; otherwise there is not enough data to call anyone absent.
    """
    with engine.connect() as conn:
        tracked = conn.execute(text(
            "SELECT COUNT(DISTINCT s.id) FROM services s JOIN attendance a ON a.service_id = s.id WHERE s.service_date >= :since"
        ), {"since": _iso(since)}).scalar()
    if tracked < min_services:
        return pd.DataFrame(columns=["id", "first_name", "last_name", "phone", "last_seen"])
    return _df(engine, """
        SELECT * FROM (
            SELECT m.id, m.first_name, m.last_name, m.phone,
                   (SELECT MAX(s.service_date) FROM attendance a JOIN services s ON s.id = a.service_id
                    WHERE a.member_id = m.id) AS last_seen
            FROM members m
            WHERE m.status IN ('Member', 'Regular attendee')
              AND NOT EXISTS (
                  SELECT 1 FROM attendance a JOIN services s ON s.id = a.service_id
                  WHERE a.member_id = m.id AND s.service_date >= :since)
        ) absent
        ORDER BY CASE WHEN last_seen IS NULL THEN 1 ELSE 0 END, last_seen, last_name
    """, since=_iso(since))


# ---------------------------------------------------------------- giving

def add_donation(engine, donation_date, amount, fund, member_id=None, method=None, notes="", recorded_by=None):
    if amount is None or float(amount) <= 0:
        raise ValueError("Amount must be greater than zero.")
    return _insert(engine, donations, member_id=member_id, donation_date=_iso(donation_date), amount=float(amount),
                   fund=fund, method=method, notes=notes, recorded_by=recorded_by)


def get_donation(engine, donation_id):
    return _one(engine, donations, donation_id)


def delete_donation(engine, donation_id):
    _delete(engine, donations, donation_id)


def list_donations(engine, start=None, end=None, member_id=None):
    sql = """
        SELECT d.id, d.donation_date, d.amount, d.fund, d.method,
               COALESCE(m.first_name || ' ' || m.last_name, 'Anonymous') AS giver,
               d.member_id, d.notes, d.recorded_by
        FROM donations d LEFT JOIN members m ON m.id = d.member_id
        WHERE 1=1
    """
    params = {}
    if start:
        sql += " AND d.donation_date >= :start"
        params["start"] = _iso(start)
    if end:
        sql += " AND d.donation_date <= :end"
        params["end"] = _iso(end)
    if member_id:
        sql += " AND d.member_id = :member_id"
        params["member_id"] = int(member_id)
    sql += " ORDER BY d.donation_date DESC, d.id DESC"
    return _df(engine, sql, **params)


# --------------------------------------------------------------- pledges

def add_pledge(engine, member_id, fund, amount, start_date, end_date, notes=""):
    if amount is None or float(amount) <= 0:
        raise ValueError("Pledge amount must be greater than zero.")
    if _iso(end_date) < _iso(start_date):
        raise ValueError("End date must be on or after the start date.")
    return _insert(engine, pledges, member_id=int(member_id), fund=fund, amount=float(amount),
                   start_date=_iso(start_date), end_date=_iso(end_date), notes=notes)


def delete_pledge(engine, pledge_id):
    _delete(engine, pledges, pledge_id)


def list_pledges(engine, member_id=None):
    """Pledges with progress: gifts by the same member to the same fund within the pledge dates."""
    sql = """
        SELECT p.id, m.first_name || ' ' || m.last_name AS member, p.fund, p.amount AS pledged,
               COALESCE((SELECT SUM(d.amount) FROM donations d
                         WHERE d.member_id = p.member_id AND d.fund = p.fund
                           AND d.donation_date BETWEEN p.start_date AND p.end_date), 0) AS given,
               p.start_date, p.end_date, p.member_id, m.phone, m.first_name, p.notes
        FROM pledges p JOIN members m ON m.id = p.member_id
    """
    params = {}
    if member_id:
        sql += " WHERE p.member_id = :member_id"
        params["member_id"] = int(member_id)
    sql += " ORDER BY p.end_date DESC, member"
    df = _df(engine, sql, **params)
    df["remaining"] = (df["pledged"] - df["given"]).clip(lower=0)
    df["progress_pct"] = (100 * df["given"] / df["pledged"]).clip(upper=100).round(0) if len(df) else []
    return df


# ---------------------------------------------------------------- events

def add_event(engine, title, event_date, start_time="", location="", description=""):
    if not (title or "").strip():
        raise ValueError("Event title is required.")
    return _insert(engine, events, title=title.strip(), event_date=_iso(event_date), start_time=start_time,
                   location=location, description=description)


def delete_event(engine, event_id):
    _delete(engine, events, event_id)


def list_events(engine, start=None):
    sql = "SELECT * FROM events"
    params = {}
    if start:
        sql += " WHERE event_date >= :start"
        params["start"] = _iso(start)
    sql += " ORDER BY event_date, start_time"
    return _df(engine, sql, **params)


# -------------------------------------------------------------- children

CHILD_FIELDS = ["first_name", "last_name", "birth_date", "class_name", "guardian_id",
                "guardian_name", "guardian_phone", "medical_notes"]


def add_child(engine, **fields):
    if not (fields.get("first_name") or "").strip() or not (fields.get("last_name") or "").strip():
        raise ValueError("Child's first and last name are required.")
    if not fields.get("guardian_id") and not (fields.get("guardian_phone") or "").strip():
        raise ValueError("Pick a parent/guardian from the members list or enter a guardian phone number.")
    values = {k: (_iso(v) if k.endswith("_date") else v) for k, v in fields.items() if k in CHILD_FIELDS}
    return _insert(engine, children, **values)


def update_child(engine, child_id, **fields):
    values = {k: (_iso(v) if k.endswith("_date") else v) for k, v in fields.items() if k in CHILD_FIELDS}
    if values:
        with engine.begin() as conn:
            conn.execute(children.update().where(children.c.id == child_id).values(**values))


def delete_child(engine, child_id):
    _delete(engine, children, child_id)


def get_child(engine, child_id):
    return _one(engine, children, child_id)


def list_children(engine):
    return _df(engine, """
        SELECT c.id, c.first_name, c.last_name, c.birth_date, c.class_name,
               COALESCE(g.first_name || ' ' || g.last_name, c.guardian_name, '') AS guardian,
               COALESCE(NULLIF(c.guardian_phone, ''), g.phone, '') AS guardian_phone,
               c.medical_notes, c.guardian_id
        FROM children c LEFT JOIN members g ON g.id = c.guardian_id
        ORDER BY c.last_name, c.first_name
    """)


def check_in_child(engine, child_id, on_date, at_time, checked_in_by=None, class_name=None, code=None):
    """Check a child in for the day and return the pickup security code.

    A child can only be checked in once per day; checking in again returns
    the existing code instead of creating a second one. Pass `code` to reuse
    a code, so siblings dropped off together share one pickup code.
    """
    with engine.begin() as conn:
        existing = conn.execute(select(child_checkins.c.security_code).where(
            child_checkins.c.child_id == child_id, child_checkins.c.checkin_date == _iso(on_date))).scalar()
        if existing:
            return existing
        if class_name is None:
            class_name = conn.execute(select(children.c.class_name).where(children.c.id == child_id)).scalar()
        used = set() if code else {r[0] for r in conn.execute(select(child_checkins.c.security_code).where(
            child_checkins.c.checkin_date == _iso(on_date)))}
        alphabet = "ACDEFGHJKMNPQRTUVWXY34679"  # no look-alike characters (0/O, 1/I, 5/S, 8/B)
        while not code or code in used:
            code = "".join(secrets.choice(alphabet) for _ in range(4))
        conn.execute(child_checkins.insert().values(
            child_id=child_id, checkin_date=_iso(on_date), class_name=class_name, security_code=code,
            checked_in_at=_iso(at_time), checked_in_by=checked_in_by))
    return code


def check_out_child(engine, checkin_id, code, at_time, picked_up_by):
    """Release a child only if the pickup code matches. Returns True on success."""
    if not (picked_up_by or "").strip():
        raise ValueError("Enter the name of the person collecting the child.")
    with engine.begin() as conn:
        row = conn.execute(select(child_checkins).where(child_checkins.c.id == checkin_id)).mappings().first()
        if not row or row["checked_out_at"]:
            return False
        if (code or "").strip().upper() != row["security_code"]:
            return False
        conn.execute(child_checkins.update().where(child_checkins.c.id == checkin_id).values(
            checked_out_at=_iso(at_time), picked_up_by=picked_up_by.strip()))
    return True


def list_checkins(engine, on_date=None, start=None, end=None):
    sql = """
        SELECT k.id, k.checkin_date, c.first_name || ' ' || c.last_name AS child, k.class_name,
               k.security_code, k.checked_in_at, k.checked_in_by, k.checked_out_at, k.picked_up_by,
               COALESCE(g.first_name || ' ' || g.last_name, c.guardian_name, '') AS guardian,
               COALESCE(NULLIF(c.guardian_phone, ''), g.phone, '') AS guardian_phone,
               c.medical_notes, k.child_id
        FROM child_checkins k JOIN children c ON c.id = k.child_id
        LEFT JOIN members g ON g.id = c.guardian_id
        WHERE 1=1
    """
    params = {}
    if on_date:
        sql += " AND k.checkin_date = :d"
        params["d"] = _iso(on_date)
    if start:
        sql += " AND k.checkin_date >= :start"
        params["start"] = _iso(start)
    if end:
        sql += " AND k.checkin_date <= :end"
        params["end"] = _iso(end)
    sql += " ORDER BY k.checkin_date DESC, k.class_name, child"
    return _df(engine, sql, **params)


# -------------------------------------------------------- backup/restore

def export_backup(engine):
    """Every data table as CSV inside one zip. User logins are left out on purpose."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        with engine.connect() as conn:
            for table in BACKUP_TABLES:
                rows = conn.execute(select(table).order_by(*table.primary_key.columns)).all()
                out = io.StringIO()
                writer = csv.writer(out)
                writer.writerow(table.columns.keys())
                writer.writerows(rows)
                zf.writestr(f"{table.name}.csv", out.getvalue())
    return buf.getvalue()


def is_empty(engine):
    """True when no church data exists yet (user logins don't count)."""
    with engine.connect() as conn:
        return all(conn.execute(select(func.count()).select_from(t)).scalar() == 0 for t in BACKUP_TABLES)


def _clean(column, value):
    if value is None or value == "" or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(column.type, Integer):
        return int(float(value))
    if isinstance(column.type, Float):
        return float(value)
    return str(value)


def restore_backup(engine, zip_bytes):
    """Load a backup made by export_backup into an EMPTY database.

    Refuses to run on a database that already has data, so a restore can
    never silently mix or overwrite records. Returns rows restored per table.
    """
    if not is_empty(engine):
        raise ValueError("Restore only works on an empty database. This one already has data.")
    counts = {}
    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        names = set(zf.namelist())
        missing = [t.name for t in BACKUP_TABLES if f"{t.name}.csv" not in names]
        if missing:
            raise ValueError(f"This does not look like a backup from this app (missing: {', '.join(missing)}).")
        with engine.begin() as conn:
            for table in BACKUP_TABLES:
                reader = csv.DictReader(io.StringIO(zf.read(f"{table.name}.csv").decode("utf-8")))
                rows = [{c.name: _clean(c, r.get(c.name)) for c in table.columns} for r in reader]
                if rows:
                    conn.execute(table.insert(), rows)
                counts[table.name] = len(rows)
            if engine.dialect.name == "postgresql":
                # Explicit ids were inserted, so move each id counter past them.
                for table in BACKUP_TABLES:
                    if "id" in table.c:
                        conn.execute(text(
                            f"SELECT setval(pg_get_serial_sequence('\"{table.name}\"', 'id'), "
                            f"COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM \"{table.name}\""))
    return counts
