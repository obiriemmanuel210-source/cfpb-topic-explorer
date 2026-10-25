"""Church management app.

Run locally with:  streamlit run church_app/app.py
"""

from datetime import timedelta

import streamlit as st

st.set_page_config(page_title="Church Manager", page_icon="⛪", layout="wide")

import auth  # noqa: E402  (set_page_config must run first)
import db  # noqa: E402
import ui  # noqa: E402
from views import admin, attendance, children, dashboard, events, giving, groups, members, messages  # noqa: E402

PAGES = {
    "Dashboard": dashboard.render,
    "Members": members.render,
    "Groups": groups.render,
    "Attendance": attendance.render,
    "Giving": giving.render,
    "Children": children.render,
    "Events": events.render,
    "Messages": messages.render,
    "Admin": admin.render,
}

MAX_FAILED_LOGINS = 5
LOCKOUT = timedelta(minutes=15)


def first_run_setup(eng):
    """No accounts exist yet: create the first admin.

    If a setup_key is configured, it must be entered, so a stranger who finds
    a freshly deployed app first cannot make themselves admin.
    """
    st.title(f"⛪ {ui.CHURCH_NAME} — first-time setup")
    setup_key = ui.setting("setup_key")
    if not setup_key:
        st.warning("No `setup_key` is configured. On a public website, set one in your secrets before this step, "
                   "otherwise whoever opens the app first can create the admin account.")
    with st.form("setup"):
        st.write("Create the first admin account. You can add other users afterwards on the Admin page.")
        key = st.text_input("Setup key", type="password") if setup_key else ""
        c1, c2 = st.columns(2)
        username = c1.text_input("Username")
        full_name = c2.text_input("Full name")
        c1, c2 = st.columns(2)
        pw1 = c1.text_input("Password", type="password")
        pw2 = c2.text_input("Repeat password", type="password")
        if st.form_submit_button("Create admin", type="primary"):
            if setup_key and key != setup_key:
                st.error("Wrong setup key.")
            elif pw1 != pw2:
                st.error("Passwords don't match.")
            elif auth.password_problem(pw1):
                st.error(auth.password_problem(pw1))
            elif db.count_users(eng):  # someone else finished setup in the meantime
                st.rerun()
            else:
                try:
                    db.add_user(eng, username, auth.hash_password(pw1), "admin", full_name)
                    ui.audit("user.add", f"{username} as admin (first-time setup)", as_user=username.strip().lower())
                    st.success("Admin created. Sign in below.")
                    st.rerun()
                except ValueError as err:
                    st.error(str(err))
    st.stop()


def login(eng):
    st.title(f"⛪ {ui.CHURCH_NAME}")
    with st.form("login"):
        username = st.text_input("Username").strip().lower()
        password = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in", type="primary"):
            failures = db.count_actions(eng, "login.failed", username, ui.now() - LOCKOUT)
            account = db.get_user(eng, username=username)
            if failures >= MAX_FAILED_LOGINS:
                st.error("Too many wrong attempts for this username. Please wait 15 minutes and try again.")
            elif account and account["active"] and auth.verify_password(password, account["password_hash"]):
                st.session_state.user = {k: account[k] for k in ("id", "username", "full_name", "role")}
                ui.audit("login", as_user=username)
                st.rerun()
            else:
                ui.audit("login.failed", as_user=username)
                st.error("Wrong username or password, or the account is disabled.")
    st.stop()


def current_user(eng):
    """The signed-in user, re-checked on every page load so disabled accounts or role changes apply at once."""
    session = st.session_state.get("user")
    if not session:
        return None
    account = db.get_user(eng, user_id=session["id"])
    if not account or not account["active"]:
        st.session_state.pop("user", None)
        return None
    st.session_state.user = {k: account[k] for k in ("id", "username", "full_name", "role")}
    return st.session_state.user


def sidebar(eng, user):
    st.sidebar.title(ui.CHURCH_NAME)
    st.sidebar.caption(f"Signed in as **{user['full_name'] or user['username']}** ({user['role']})")
    allowed = [p for p in PAGES if auth.can(user["role"], p)]
    page = st.sidebar.radio("Go to", allowed)
    with st.sidebar.expander("Change my password"):
        with st.form("my_pw", clear_on_submit=True):
            old = st.text_input("Current password", type="password")
            new = st.text_input("New password", type="password")
            if st.form_submit_button("Change"):
                account = db.get_user(eng, user_id=user["id"])
                if not auth.verify_password(old, account["password_hash"]):
                    st.error("Current password is wrong.")
                elif auth.password_problem(new):
                    st.error(auth.password_problem(new))
                else:
                    db.update_user(eng, user["id"], password_hash=auth.hash_password(new))
                    ui.audit("user.password_change")
                    st.success("Password changed.")
    if st.sidebar.button("Sign out"):
        st.session_state.clear()
        st.rerun()
    return page


eng = ui.engine()
if not db.count_users(eng):
    first_run_setup(eng)
user = current_user(eng)
if not user:
    login(eng)
PAGES[sidebar(eng, user)]()
