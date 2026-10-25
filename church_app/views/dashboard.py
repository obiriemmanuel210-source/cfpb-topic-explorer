from datetime import timedelta

import plotly.express as px
import streamlit as st

import auth
import db
import ui


def render():
    eng = ui.engine()
    role = ui.user()["role"]
    today = ui.today()
    st.title(f"⛪ {ui.CHURCH_NAME}")

    people = db.list_members(eng)
    services = db.list_services(eng, start=today - timedelta(weeks=12))
    sundays = services[services["service_type"] == "Sunday service"]

    cols = st.columns(4 if auth.sees_giving(role) else 3)
    cols[0].metric("Members", int((people["status"] == "Member").sum()))
    cols[1].metric("Everyone on file", len(people))
    cols[2].metric("Avg Sunday attendance (12 wks)", f"{sundays['headcount'].mean():.0f}" if len(sundays) else "—")
    giving_month = None
    if auth.sees_giving(role):
        giving_month = db.list_donations(eng, start=today.replace(day=1), end=today)
        cols[3].metric("Giving this month", ui.money(giving_month["amount"].sum()))

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
        if giving_month is not None:
            st.subheader("Giving by fund (this month)")
            if giving_month.empty:
                st.info("No giving recorded this month.")
            else:
                by_fund = giving_month.groupby("fund", as_index=False)["amount"].sum()
                st.plotly_chart(px.pie(by_fund, names="fund", values="amount", hole=0.45), width="stretch")
        else:
            st.subheader("📅 Upcoming events")
            _events(eng, today)

    left, right = st.columns(2)
    with left:
        st.subheader("🎂 Birthdays in the next 30 days")
        bdays = db.upcoming_birthdays(eng, today)
        if bdays.empty:
            st.caption("None — add birth dates on the Members page to see them here.")
        else:
            st.dataframe(bdays[["name", "birthday", "in_days", "phone"]], hide_index=True, width="stretch")
    with right:
        if giving_month is not None:
            st.subheader("📅 Upcoming events")
            _events(eng, today)

    st.subheader("🔔 Follow up: members not seen in 4 weeks")
    absent = db.absent_members(eng, since=today - timedelta(weeks=4))
    if absent.empty:
        st.caption("Nobody to follow up (or not enough check-in data yet — at least 3 services with names checked in).")
    else:
        st.dataframe(absent.drop(columns="id"), hide_index=True, width="stretch")
        st.caption("Send them a message from the Messages page.")


def _events(eng, today):
    upcoming = db.list_events(eng, start=today).head(5)
    if upcoming.empty:
        st.caption("No upcoming events.")
    else:
        st.dataframe(upcoming[["event_date", "start_time", "title", "location"]], hide_index=True, width="stretch")
