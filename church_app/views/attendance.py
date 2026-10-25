from datetime import timedelta

import plotly.express as px
import streamlit as st

import db
import ui


def render():
    eng = ui.engine()
    st.title("🙌 Attendance")
    tab_record, tab_history = st.tabs(["Record a service", "History"])

    with tab_record:
        c1, c2 = st.columns(2)
        service_date = c1.date_input("Date", ui.today(), key="svc_date")
        service_type = c2.selectbox("Service", db.SERVICE_TYPES)
        existing = db.get_service(eng, service_date, service_type) or {}
        if existing:
            st.info("This service already has a record — saving will update it.")

        options = ui.member_options()
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
                db.record_service(eng, service_date, service_type, headcount, notes, present)
                ui.audit("attendance.save", f"{service_date} {service_type}: {max(headcount, len(present))}")
                st.success(f"Saved: {max(headcount, len(present))} in attendance, {len(present)} members checked in.")

    with tab_history:
        c1, c2 = st.columns(2)
        start = c1.date_input("From", ui.today() - timedelta(weeks=12), key="att_from")
        end = c2.date_input("To", ui.today(), key="att_to")
        history = db.list_services(eng, start, end)
        if history.empty:
            st.info("No services in this range.")
            return
        st.plotly_chart(
            px.bar(history.sort_values("service_date"), x="service_date", y="headcount", color="service_type",
                   barmode="group", labels={"service_date": "", "headcount": "Headcount"}),
            width="stretch",
        )
        st.dataframe(history.drop(columns="id"), hide_index=True, width="stretch")
        ui.download_button(history, "attendance.csv")
