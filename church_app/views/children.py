from datetime import date, timedelta

import streamlit as st

import db
import ui


def render():
    eng = ui.engine()
    st.title("🧒 Children's ministry")
    tab_in, tab_out, tab_register, tab_history = st.tabs(["Check in", "Today / check out", "Children", "History"])
    today = ui.today()
    kids = db.list_children(eng)

    with tab_in:
        if kids.empty:
            st.info("No children registered yet. Add them in the 'Children' tab.")
        else:
            here = set(db.list_checkins(eng, on_date=today)["child_id"])
            waiting = kids[~kids["id"].isin(here)]
            labels = {int(r.id): f"{r.first_name} {r.last_name} — {r.class_name or 'no class'} (guardian: {r.guardian or '?'})"
                      for r in waiting.itertuples()}
            chosen = st.multiselect("Children arriving (type to search)", list(labels), format_func=labels.get,
                                    help="Select siblings together — they will share one pickup code.")
            if st.button("Check in", type="primary", disabled=not chosen):
                code = None
                for child_id in chosen:  # siblings share the first child's code
                    code = db.check_in_child(eng, child_id, today, ui.now(), ui.username(), code=code)
                ui.audit("children.checkin", f"{len(chosen)} child(ren), code {code}")
                st.session_state.last_code = (code, chosen)
                st.rerun()

            def medical_alerts(child_ids):
                for r in kids[kids["id"].isin(child_ids) & kids["medical_notes"].fillna("").ne("")].itertuples():
                    st.warning(f"⚠️ {r.first_name} {r.last_name}: {r.medical_notes}")

            medical_alerts(chosen)
            if st.session_state.get("last_code"):
                code, done_ids = st.session_state.last_code
                names = kids[kids["id"].isin(done_ids)]
                st.success("Checked in: " + ", ".join(names["first_name"] + " " + names["last_name"]))
                st.markdown(f"### Pickup code: `{code}`")
                st.caption("Write this on the child's label and give the same code to the parent. "
                           "The child is only released to someone who shows this code.")
                medical_alerts(done_ids)

    with tab_out:
        rows = db.list_checkins(eng, on_date=today)
        if rows.empty:
            st.info("No children checked in today.")
        else:
            inside = rows[rows["checked_out_at"].isna()]
            st.metric("In the children's area now", len(inside), help=f"{len(rows)} checked in today in total")
            for r in inside.itertuples():
                with st.container(border=True):
                    st.markdown(f"**{r.child}** · {r.class_name or ''} · in at {str(r.checked_in_at)[11:16]}  \n"
                                f"Guardian: {r.guardian} {r.guardian_phone}")
                    if r.medical_notes:
                        st.caption(f"⚠️ {r.medical_notes}")
                    with st.form(f"out_{r.id}"):
                        c1, c2, c3 = st.columns([1, 2, 1])
                        code = c1.text_input("Pickup code", max_chars=4)
                        by = c2.text_input("Collected by (name)")
                        if c3.form_submit_button("Check out"):
                            try:
                                if db.check_out_child(eng, r.id, code, ui.now(), by):
                                    ui.audit("children.checkout", f"{r.child} collected by {by}")
                                    st.rerun()
                                else:
                                    st.error("Code does not match. Do not release the child — call the guardian or a leader.")
                            except ValueError as err:
                                st.error(str(err))
            done = rows[rows["checked_out_at"].notna()]
            if len(done):
                st.subheader("Already collected")
                st.dataframe(done[["child", "class_name", "checked_in_at", "checked_out_at", "picked_up_by"]],
                             hide_index=True, width="stretch")

    with tab_register:
        _register(eng, kids)

    with tab_history:
        c1, c2 = st.columns(2)
        start = c1.date_input("From", today - timedelta(weeks=8), key="kid_from")
        end = c2.date_input("To", today, key="kid_to")
        hist = db.list_checkins(eng, start=start, end=end)
        if hist.empty:
            st.info("No check-ins in this range.")
        else:
            per_day = hist.groupby(["checkin_date", "class_name"], dropna=False).size().reset_index(name="children")
            st.dataframe(per_day, hide_index=True, width="stretch")
            ui.download_button(hist.drop(columns=["security_code", "child_id"]), "children_checkins.csv", key="dl_kids")


def _register(eng, kids):
    options = ui.member_options()
    with st.form("child", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        first = c1.text_input("First name *")
        last = c2.text_input("Last name *")
        born = c3.date_input("Birth date", None, min_value=date(2005, 1, 1), max_value=ui.today())
        c1, c2 = st.columns(2)
        class_name = c1.selectbox("Class", db.CHILDREN_CLASSES)
        guardian = c2.selectbox("Parent / guardian (member)", [None, *options],
                                format_func=lambda i: "— not a member —" if i is None else options[i])
        c1, c2 = st.columns(2)
        g_name = c1.text_input("Guardian name (if not a member)")
        g_phone = c2.text_input("Guardian phone (if not a member, or a different number)")
        medical = st.text_input("Allergies / medical notes", placeholder="e.g. peanut allergy, asthma inhaler in bag")
        if st.form_submit_button("Register child", type="primary"):
            try:
                db.add_child(eng, first_name=first.strip(), last_name=last.strip(), birth_date=born, class_name=class_name,
                             guardian_id=guardian, guardian_name=g_name.strip(), guardian_phone=g_phone.strip(),
                             medical_notes=medical.strip())
                ui.audit("children.register", f"{first} {last}")
                st.success(f"Registered {first} {last}.")
                st.rerun()
            except ValueError as err:
                st.error(str(err))

    if kids.empty:
        return
    st.dataframe(kids[["first_name", "last_name", "birth_date", "class_name", "guardian", "guardian_phone", "medical_notes"]],
                 hide_index=True, width="stretch")
    labels = {int(r.id): f"{r.first_name} {r.last_name}" for r in kids.itertuples()}
    with st.expander("Change a child's class or remove a child"):
        child_id = st.selectbox("Child", list(labels), format_func=labels.get)
        child = db.get_child(eng, child_id)
        c1, c2 = st.columns(2)
        new_class = c1.selectbox("Class", db.CHILDREN_CLASSES,
                                 index=db.CHILDREN_CLASSES.index(child["class_name"]) if child["class_name"] in db.CHILDREN_CLASSES else 0)
        if c2.button("Save class"):
            db.update_child(eng, child_id, class_name=new_class)
            st.rerun()
        if ui.confirm_button("Remove child", f"del_child_{child_id}", "Removes the child and their check-in history."):
            db.delete_child(eng, child_id)
            ui.audit("children.delete", labels[child_id])
            st.rerun()
