from datetime import date

import streamlit as st

import auth
import db
import ui


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
        birth = c1.date_input("Birth date", as_date(e.get("birth_date")), min_value=date(1900, 1, 1), max_value=ui.today())
        joined = c2.date_input("Join date", as_date(e.get("join_date")), min_value=date(1900, 1, 1))
        ministry = c3.text_input("Role / title", e.get("ministry") or "", placeholder="e.g. Deacon, Elder, Usher")
        address = st.text_input("Address", e.get("address") or "")
        notes = st.text_area("Notes", e.get("notes") or "")
        if st.form_submit_button("Save member", type="primary"):
            return dict(first_name=first.strip(), last_name=last.strip(), gender=gender or None, phone=phone.strip(),
                        email=email.strip(), status=status, birth_date=birth, join_date=joined, ministry=ministry,
                        address=address, notes=notes)
    return None


def render():
    eng = ui.engine()
    role = ui.user()["role"]
    editable = auth.can_edit_members(role)
    st.title("👥 Members")
    tabs = st.tabs(["Directory", "Add member", "Edit / remove"] if editable else ["Directory"])

    with tabs[0]:
        c1, c2 = st.columns([3, 1])
        search = c1.text_input("Search by name, phone or email")
        status = c2.selectbox("Status", ["All", *db.MEMBER_STATUSES])
        people = db.list_members(eng, search, None if status == "All" else status)
        st.caption(f"{len(people)} people")
        cols = ["first_name", "last_name", "phone", "email", "status", "ministry", "birth_date", "join_date"]
        st.dataframe(people[cols], hide_index=True, width="stretch")
        ui.download_button(people, "members.csv")
        if not editable:
            st.caption("Your role can view members but not change them.")
            return

    with tabs[1]:
        data = member_form("add_member")
        if data:
            try:
                new_id = db.add_member(eng, **data)
                ui.audit("member.add", f"#{new_id} {data['first_name']} {data['last_name']}")
                st.success(f"Added {data['first_name']} {data['last_name']}.")
            except ValueError as err:
                st.error(str(err))

    with tabs[2]:
        options = ui.member_options()
        if not options:
            st.info("No members yet.")
            return
        member_id = st.selectbox("Choose a member", list(options), format_func=options.get)
        existing = db.get_member(eng, member_id)
        data = member_form(f"edit_{member_id}", existing)
        if data:
            if not data["first_name"] or not data["last_name"]:
                st.error("First and last name are required.")
            else:
                db.update_member(eng, member_id, **data)
                ui.audit("member.edit", f"#{member_id} {data['first_name']} {data['last_name']}")
                st.success("Saved.")
                st.rerun()

        in_groups = db.member_groups(eng, member_id)
        st.markdown("**Groups:** " + (", ".join(in_groups["name"]) if len(in_groups) else "none — add them on the Groups page"))

        with st.expander("Remove this member"):
            if ui.confirm_button("Delete member", f"del_member_{member_id}",
                                 "This permanently deletes the member, their attendance and pledges. "
                                 "Their past gifts are kept as anonymous so totals stay correct."):
                db.delete_member(eng, member_id)
                ui.audit("member.delete", f"#{member_id} {existing['first_name']} {existing['last_name']}")
                st.success("Member removed.")
                st.rerun()
