import streamlit as st

import db
import ui


def render():
    eng = ui.engine()
    st.title("📅 Events")
    with st.form("event", clear_on_submit=True):
        title = st.text_input("Title *")
        c1, c2, c3 = st.columns(3)
        event_date = c1.date_input("Date", ui.today())
        start_time = c2.time_input("Start time", value=None)
        location = c3.text_input("Location")
        description = st.text_area("Description")
        if st.form_submit_button("Add event", type="primary"):
            try:
                db.add_event(eng, title, event_date, start_time.strftime("%H:%M") if start_time else "", location, description)
                ui.audit("event.add", f"{event_date} {title}")
                st.success("Event added.")
            except ValueError as err:
                st.error(str(err))

    show_past = st.toggle("Show past events")
    listing = db.list_events(eng, None if show_past else ui.today())
    if listing.empty:
        st.info("No events.")
        return
    for e in listing.itertuples():
        with st.container(border=True):
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"**{e.title}** — {e.event_date} {e.start_time or ''}  \n{e.location or ''}")
            if e.description:
                c1.caption(e.description)
            if c2.button("Delete", key=f"del_event_{e.id}"):
                db.delete_event(eng, e.id)
                ui.audit("event.delete", f"{e.event_date} {e.title}")
                st.rerun()
