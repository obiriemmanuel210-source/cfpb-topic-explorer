import streamlit as st

import db
import ui


def render():
    eng = ui.engine()
    st.title("🫂 Groups")
    st.caption("Cells, home groups, ministries and departments (e.g. Choir, Ushers, Youth). A person can be in several.")
    tab_view, tab_new = st.tabs(["Groups", "New group"])
    options = ui.member_options()

    with tab_new:
        with st.form("new_group", clear_on_submit=True):
            c1, c2 = st.columns(2)
            name = c1.text_input("Group name *")
            kind = c2.selectbox("Type", db.GROUP_KINDS)
            c1, c2 = st.columns(2)
            leader = c1.selectbox("Leader", [None, *options], format_func=lambda i: "—" if i is None else options[i])
            meeting = c2.text_input("Meets", placeholder="e.g. Thursdays 6:30pm at Elder Mensah's house")
            notes = st.text_area("Notes")
            if st.form_submit_button("Create group", type="primary"):
                try:
                    gid = db.add_group(eng, name, kind, leader, meeting, notes)
                    if leader:
                        db.set_group_members(eng, gid, [leader])
                    ui.audit("group.add", name)
                    st.success(f"Created {name}. Add members under the Groups tab.")
                except ValueError as err:
                    st.error(str(err))

    with tab_view:
        all_groups = db.list_groups(eng)
        if all_groups.empty:
            st.info("No groups yet. Create one in the 'New group' tab.")
            return
        st.dataframe(all_groups[["name", "kind", "leader", "members", "meeting_time"]], hide_index=True, width="stretch")

        labels = dict(zip(all_groups["id"].astype(int), all_groups["name"]))
        group_id = st.selectbox("Open a group", list(labels), format_func=labels.get)
        group = db.get_group(eng, group_id)

        with st.form(f"group_members_{group_id}"):
            current = [m for m in db.group_member_ids(eng, group_id) if m in options]
            chosen = st.multiselect("Members of this group (type to search)", list(options), default=current,
                                    format_func=options.get)
            c1, c2 = st.columns(2)
            leader_opts = [None, *options]
            leader = c1.selectbox("Leader", leader_opts, format_func=lambda i: "—" if i is None else options[i],
                                  index=leader_opts.index(group["leader_id"]) if group["leader_id"] in options else 0)
            meeting = c2.text_input("Meets", group["meeting_time"] or "")
            if st.form_submit_button("Save group", type="primary"):
                db.set_group_members(eng, group_id, chosen)
                db.update_group(eng, group_id, leader_id=leader, meeting_time=meeting)
                ui.audit("group.edit", f"{group['name']}: {len(chosen)} members")
                st.success("Saved.")
                st.rerun()

        roster = db.list_group_members(eng, group_id)
        ui.download_button(roster, f"{group['name']}.csv", "Download member list", key=f"dl_group_{group_id}")

        with st.expander("Delete this group"):
            if ui.confirm_button("Delete group", f"del_group_{group_id}",
                                 "Deletes the group only. The people in it stay in the member list."):
                db.delete_group(eng, group_id)
                ui.audit("group.delete", group["name"])
                st.rerun()
