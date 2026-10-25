"""Shared helpers for the Streamlit pages: settings, database, current user."""

import os
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

import db


def setting(name, default=None):
    """Read a setting from Streamlit secrets first, then environment variables."""
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:  # no secrets.toml present
        pass
    return os.environ.get(name.upper(), default)


CHURCH_NAME = setting("church_name", "Our Church")
CURRENCY = setting("currency", "$")
TIMEZONE = ZoneInfo(setting("timezone", "Africa/Accra"))


@st.cache_resource
def get_engine():
    return db.connect(setting("database_url") or setting("db_path") or db.DEFAULT_DB_PATH)


def engine():
    return get_engine()


def now():
    """Local church time, not the server's clock (cloud servers run on UTC)."""
    return datetime.now(TIMEZONE).replace(tzinfo=None, microsecond=0)


def today():
    return now().date()


def user():
    return st.session_state.get("user")


def username():
    u = user()
    return u["username"] if u else None


def audit(action, details="", as_user=None):
    db.log(engine(), as_user or username(), action, details, at=now())


def money(value):
    return f"{CURRENCY}{value:,.2f}"


def member_options(engine_=None):
    """Map of member id -> display label, used by every member picker."""
    people = db.list_members(engine_ or engine())
    return {int(r.id): f"{r.first_name} {r.last_name}" + (f" ({r.phone})" if r.phone else "") for r in people.itertuples()}


def download_button(df, filename, label="Download CSV", key=None):
    st.download_button(label, df.to_csv(index=False).encode(), file_name=filename, mime="text/csv", key=key)


def confirm_button(label, key, warning):
    """A delete button that needs a tick first, to avoid accidental clicks."""
    st.warning(warning)
    sure = st.checkbox("I understand", key=f"{key}_sure")
    return st.button(label, key=key, disabled=not sure)
