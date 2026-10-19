"""Church management app: members, attendance, giving and events.

Run locally with:  streamlit run church_app/app.py
"""

import os
from datetime import date, timedelta

import pandas as pd
import plotly.express as px
import streamlit as st

import db

st.set_page_config(page_title="Church Manager", page_icon="⛪", layout="wide")


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
PASSWORD = setting("app_password")


def money(value):
    return f"{CURRENCY}{value:,.2f}"


# ------------------------------------------------------------------ auth

def require_login():
    """Simple shared-password gate. Skipped (with a warning) if no password is set."""
    if not PASSWORD:
        st.sidebar.warning("No app_password set — anyone with the link can see this data.")
        return
    if st.session_state.get("authed"):
        return
    st.title(f"⛪ {CHURCH_NAME}")
    with st.form("login"):
        entered = st.text_input("Password", type="password")
        if st.form_submit_button("Sign in"):
            if entered == PASSWORD:
                st.session_state.authed = True
                st.rerun()
            st.error("Incorrect password.")
    st.stop()


@st.cache_resource
def get_conn():
    return db.connect(setting("db_path", db.DEFAULT_DB_PATH))


require_login()
conn = get_conn()


def member_options():
    """Map of member id -> display label, used by every member picker."""
    members = db.list_members(conn)
    return {int(r.id): f"{r.first_name} {r.last_name}" + (f" ({r.phone})" if r.phone else "") for r in members.itertuples()}


def download_button(df, filename, label="Download CSV"):
    st.download_button(label, df.to_csv(index=False).encode(), file_name=filename, mime="text/csv")


# ------------------------------------------------------------- dashboard

def page_dashboard():
    st.title(f"⛪ {CHURCH_NAME}")
    today = date.today()
    month_start = today.replace(day=1)

    members = db.list_members(conn)
    services = db.list_services(conn, start=today - timedelta(weeks=12))
    giving_month = db.list_donations(conn, start=month_start, end=today)
    sundays = services[services["service_type"] == "Sunday service"]

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Members", int((members["status"] == "Member").sum()))
    c2.metric("Everyone on file", len(members))
    c3.metric("Avg Sunday attendance (12 wks)", f"{sundays['headcount'].mean():.0f}" if len(sundays) else "—")
    c4.metric(f"Giving this month", money(giving_month["amount"].sum()))

    left, right = st.columns(2)
    with left:
        st.subheader("Attendance trend")
        if services.empty:
            st.info("No services recorded yet. Use the Attendance page to add one.")
        else:
            fig = px.line(services.sort_values("service_date"), x="service_date", y="headcount",
                          color="service_type", markers=True, labels={"service_date": "", "headcount": "Headcount"})
            st.plotly_chart(fig, width="stretch")
    with right:
        st.subheader("Giving by fund (this month)")
        if giving_month.empty:
            st.info("No giving recorded this month.")
        else:
            by_fund = giving_month.groupby("fund", as_index=False)["amount"].sum()
            st.plotly_chart(px.pie(by_fund, names="fund", values="amount", hole=0.45), width="stretch")

    left, right = st.columns(2)
    with left:
        st.subheader("🎂 Birthdays in the next 30 days")
        bdays = db.upcoming_birthdays(conn, today)
        if bdays.empty:
            st.caption("None — add birth dates on the Members page to see them here.")
        else:
            st.dataframe(bdays, hide_index=True, width="stretch")
    with right:
        st.subheader("📅 Upcoming events")
        events = db.list_events(conn, start=today).head(5)
        if events.empty:
            st.caption("No upcoming events.")
        else:
            st.dataframe(events[["event_date", "start_time", "title", "location"]], hide_index=True, width="stretch")

    st.subheader("🔔 Follow up: members not seen in 4 weeks")
    absent = db.absent_members(conn, since=today - timedelta(weeks=4))
    if absent.empty:
        st.caption("Nobody to follow up (or not enough check-in data yet — at least 3 services with names checked in).")
    else:
        st.dataframe(absent, hide_index=True, width="stretch")


# --------------------------------------------------------------- members

def member_form(key, existing=None):
    """Shared add/edit form. Returns the field dict on submit, else None."""
    e = existing or {}

    def as_date(value):
        return date.fromisoformat(value) if value else None

    with st.form(key, clear_on_submit=existing is None):
        c1, c2, c3 = st.columns(3)
        first = c1.text_input("First name *", e.get("first_name", ""))
        last = c2.text_input("Last name *", e.get("last_name", ""))
        genders = ["", "Female", "Male"]
        gender = c3.selectbox("Gender", genders, index=genders.index(e.get("gender") or ""))
        c1, c2, c3 = st.columns(3)
        phone = c1.text_input("Phone", e.get("phone") or "")
        email = c2.text_input("Email", e.get("email") or "")
        status = c3.selectbox("Status", db.MEMBER_STATUSES, index=db.MEMBER_STATUSES.index(e.get("status") or "Member"))
        c1, c2, c3 = st.columns(3)
        birth = c1.date_input("Birth date", as_date(e.get("birth_date")), min_value=date(1900, 1, 1), max_value=date.today())
        joined = c2.date_input("Join date", as_date(e.get("join_date")), min_value=date(1900, 1, 1))
        ministry = c3.text_input("Ministry / group", e.get("ministry") or "", placeholder="e.g. Choir, Ushers, Youth")
        address = st.text_input("Address", e.get("address") or "")
        notes = st.text_area("Notes", e.get("notes") or "")
        if st.form_submit_button("Save member", type="primary"):
            return dict(first_name=first.strip(), last_name=last.strip(), gender=gender or None, phone=phone,
                        email=email, status=status, birth_date=birth, join_date=joined, ministry=ministry,
                        address=address, notes=notes)
    return None


def page_members():
    st.title("👥 Members")
    tab_list, tab_add, tab_edit = st.tabs(["Directory", "Add member", "Edit / remove"])

    with tab_list:
        c1, c2 = st.columns([3, 1])
        search = c1.text_input("Search by name, phone or email")
        status = c2.selectbox("Status", ["All", *db.MEMBER_STATUSES])
        members = db.list_members(conn, search, None if status == "All" else status)
        st.caption(f"{len(members)} people")
        cols = ["first_name", "last_name", "phone", "email", "status", "ministry", "birth_date", "join_date"]
        st.dataframe(members[cols], hide_index=True, width="stretch")
        download_button(members, "members.csv")

    with tab_add:
        data = member_form("add_member")
        if data:
            try:
                db.add_member(conn, **data)
                st.success(f"Added {data['first_name']} {data['last_name']}.")
            except ValueError as err:
                st.error(str(err))

    with tab_edit:
        options = member_options()
        if not options:
            st.info("No members yet.")
            return
        member_id = st.selectbox("Choose a member", list(options), format_func=options.get)
        existing = db.get_member(conn, member_id)
        data = member_form(f"edit_{member_id}", existing)
        if data:
            if not data["first_name"] or not data["last_name"]:
                st.error("First and last name are required.")
            else:
                db.update_member(conn, member_id, **data)
                st.success("Saved.")
                st.rerun()

        st.divider()
        giving = db.list_donations(conn, member_id=member_id)
        st.markdown(f"**Giving on record:** {money(giving['amount'].sum())} across {len(giving)} gifts")
        if not giving.empty:
            download_button(giving, f"giving_statement_{member_id}.csv", "Download giving statement")

        with st.expander("Remove this member"):
            st.warning("This permanently deletes the member and their attendance records. Their past gifts are kept as anonymous.")
            if st.checkbox("I understand", key=f"confirm_del_{member_id}") and st.button("Delete member"):
                db.delete_member(conn, member_id)
                st.success("Member removed.")
                st.rerun()


# ------------------------------------------------------------ attendance

def page_attendance():
    st.title("🙌 Attendance")
    tab_record, tab_history = st.tabs(["Record a service", "History"])

    with tab_record:
        c1, c2 = st.columns(2)
        service_date = c1.date_input("Date", date.today(), key="svc_date")
        service_type = c2.selectbox("Service", db.SERVICE_TYPES)
        existing = db.get_service(conn, service_date, service_type) or {}
        if existing:
            st.info("This service already has a record — saving will update it.")

        options = member_options()
        with st.form(f"service_{service_date}_{service_type}"):
            present = st.multiselect(
                "Members present (type to search)", list(options), format_func=options.get,
                default=[m for m in existing.get("member_ids", []) if m in options],
            )
            headcount = st.number_input(
                "Total headcount (including visitors and children)", min_value=0, step=1,
                value=int(existing.get("headcount", 0)),
                help="If this is lower than the number of members ticked, the member count is used.",
            )
            notes = st.text_input("Notes", existing.get("notes") or "", placeholder="Preacher, theme, anything notable")
            if st.form_submit_button("Save attendance", type="primary"):
                db.record_service(conn, service_date, service_type, headcount, notes, present)
                st.success(f"Saved: {max(headcount, len(present))} in attendance, {len(present)} members checked in.")

    with tab_history:
        c1, c2 = st.columns(2)
        start = c1.date_input("From", date.today() - timedelta(weeks=12), key="att_from")
        end = c2.date_input("To", date.today(), key="att_to")
        services = db.list_services(conn, start, end)
        if services.empty:
            st.info("No services in this range.")
            return
        st.plotly_chart(
            px.bar(services.sort_values("service_date"), x="service_date", y="headcount", color="service_type",
                   barmode="group", labels={"service_date": "", "headcount": "Headcount"}),
            width="stretch",
        )
        st.dataframe(services.drop(columns="id"), hide_index=True, width="stretch")
        download_button(services, "attendance.csv")


# ---------------------------------------------------------------- giving

def page_giving():
    st.title("💰 Giving")
    tab_add, tab_report = st.tabs(["Record giving", "Reports"])

    with tab_add:
        options = {0: "Anonymous / loose offering", **member_options()}
        with st.form("donation", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            giver = c1.selectbox("Giver", list(options), format_func=options.get)
            amount = c2.number_input(f"Amount ({CURRENCY})", min_value=0.0, step=1.0, format="%.2f")
            gift_date = c3.date_input("Date", date.today())
            c1, c2 = st.columns(2)
            fund = c1.selectbox("Fund", db.GIVING_FUNDS)
            method = c2.selectbox("Method", db.PAYMENT_METHODS)
            notes = st.text_input("Notes / reference")
            if st.form_submit_button("Save", type="primary"):
                try:
                    db.add_donation(conn, gift_date, amount, fund, giver or None, method, notes)
                    st.success(f"Recorded {money(amount)} to {fund}.")
                except ValueError as err:
                    st.error(str(err))

    with tab_report:
        c1, c2 = st.columns(2)
        start = c1.date_input("From", date.today().replace(day=1), key="giv_from")
        end = c2.date_input("To", date.today(), key="giv_to")
        gifts = db.list_donations(conn, start, end)
        if gifts.empty:
            st.info("No giving in this range.")
            return
        c1, c2, c3 = st.columns(3)
        c1.metric("Total", money(gifts["amount"].sum()))
        c2.metric("Gifts", len(gifts))
        c3.metric("Named givers", gifts["member_id"].nunique())

        left, right = st.columns(2)
        by_fund = gifts.groupby("fund", as_index=False)["amount"].sum().sort_values("amount", ascending=False)
        left.dataframe(by_fund, hide_index=True, width="stretch")
        by_week = gifts.assign(week=pd.to_datetime(gifts["donation_date"]).dt.to_period("W").dt.start_time)
        by_week = by_week.groupby(["week", "fund"], as_index=False)["amount"].sum()
        right.plotly_chart(px.bar(by_week, x="week", y="amount", color="fund", labels={"week": "Week of", "amount": ""}),
                           width="stretch")

        st.dataframe(gifts.drop(columns=["member_id"]), hide_index=True, width="stretch")
        download_button(gifts, f"giving_{start}_{end}.csv")

        with st.expander("Delete an entry (for corrections)"):
            gift_id = st.selectbox("Entry", gifts["id"], format_func=lambda i: (
                lambda r: f"#{i} · {r.donation_date} · {r.giver} · {money(r.amount)} · {r.fund}"
            )(gifts.set_index("id").loc[i]))
            if st.button("Delete entry"):
                db.delete_donation(conn, int(gift_id))
                st.rerun()


# ---------------------------------------------------------------- events

def page_events():
    st.title("📅 Events")
    with st.form("event", clear_on_submit=True):
        title = st.text_input("Title *")
        c1, c2, c3 = st.columns(3)
        event_date = c1.date_input("Date", date.today())
        start_time = c2.time_input("Start time", value=None)
        location = c3.text_input("Location")
        description = st.text_area("Description")
        if st.form_submit_button("Add event", type="primary"):
            try:
                db.add_event(conn, title, event_date, start_time.strftime("%H:%M") if start_time else "", location, description)
                st.success("Event added.")
            except ValueError as err:
                st.error(str(err))

    show_past = st.toggle("Show past events")
    events = db.list_events(conn, None if show_past else date.today())
    if events.empty:
        st.info("No events.")
        return
    for e in events.itertuples():
        with st.container(border=True):
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"**{e.title}** — {e.event_date} {e.start_time or ''}  \n{e.location or ''}")
            if e.description:
                c1.caption(e.description)
            if c2.button("Delete", key=f"del_event_{e.id}"):
                db.delete_event(conn, e.id)
                st.rerun()


PAGES = {
    "Dashboard": page_dashboard,
    "Members": page_members,
    "Attendance": page_attendance,
    "Giving": page_giving,
    "Events": page_events,
}

st.sidebar.title(CHURCH_NAME)
PAGES[st.sidebar.radio("Go to", list(PAGES))]()
