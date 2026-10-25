import streamlit as st

import auth
import db
import ui


def render():
    eng = ui.engine()
    st.title("🔐 Admin")
    tab_users, tab_backup, tab_audit = st.tabs(["User accounts", "Backup & restore", "Audit log"])

    with tab_users:
        _users(eng)
    with tab_backup:
        _backup(eng)
    with tab_audit:
        log = db.list_audit(eng)
        st.caption("Every change made in the app, newest first, with who made it.")
        st.dataframe(log, hide_index=True, width="stretch")
        ui.download_button(log, "audit_log.csv", key="dl_audit")


def _users(eng):
    st.markdown("\n".join(f"- **{r}** — {d.split(': ', 1)[1]}" for r, d in auth.ROLES.items()))
    accounts = db.list_users(eng)
    st.dataframe(accounts.drop(columns="id"), hide_index=True, width="stretch")

    with st.expander("Add a user", expanded=len(accounts) < 2):
        with st.form("add_user", clear_on_submit=True):
            c1, c2 = st.columns(2)
            username = c1.text_input("Username")
            full_name = c2.text_input("Full name")
            c1, c2 = st.columns(2)
            role = c1.selectbox("Role", list(auth.ROLES))
            password = c2.text_input("Temporary password", type="password",
                                     help=f"At least {auth.MIN_PASSWORD_LENGTH} characters. Ask them to change it after signing in.")
            if st.form_submit_button("Create user", type="primary"):
                problem = auth.password_problem(password)
                if problem:
                    st.error(problem)
                else:
                    try:
                        db.add_user(eng, username, auth.hash_password(password), role, full_name)
                        ui.audit("user.add", f"{username} as {role}")
                        st.success(f"Created {username}.")
                        st.rerun()
                    except ValueError as err:
                        st.error(str(err))

    if accounts.empty:
        return
    with st.expander("Change a user"):
        labels = {int(r.id): f"{r.username} ({r.role}{'' if r.active else ', disabled'})" for r in accounts.itertuples()}
        uid = st.selectbox("User", list(labels), format_func=labels.get)
        target = db.get_user(eng, user_id=uid)
        me = ui.user()["id"] == uid
        active_admins = int(((accounts["role"] == "admin") & (accounts["active"] == 1)).sum())
        last_admin = target["role"] == "admin" and target["active"] and active_admins <= 1

        c1, c2 = st.columns(2)
        new_role = c1.selectbox("Role", list(auth.ROLES), index=list(auth.ROLES).index(target["role"]), key=f"role_{uid}")
        if c1.button("Save role", key=f"save_role_{uid}"):
            if last_admin and new_role != "admin":
                st.error("This is the last admin. Make someone else an admin first.")
            else:
                db.update_user(eng, uid, role=new_role)
                ui.audit("user.role", f"{target['username']} -> {new_role}")
                st.rerun()
        new_pw = c2.text_input("New password", type="password", key=f"pw_{uid}")
        if c2.button("Reset password", key=f"reset_{uid}"):
            problem = auth.password_problem(new_pw)
            if problem:
                st.error(problem)
            else:
                db.update_user(eng, uid, password_hash=auth.hash_password(new_pw))
                ui.audit("user.password_reset", target["username"])
                st.success("Password changed.")

        if target["active"]:
            if me or last_admin:
                st.caption("You can't disable your own account or the last admin.")
            elif st.button("Disable this account", key=f"disable_{uid}"):
                db.update_user(eng, uid, active=0)
                ui.audit("user.disable", target["username"])
                st.rerun()
        elif st.button("Re-enable this account", key=f"enable_{uid}"):
            db.update_user(eng, uid, active=1)
            ui.audit("user.enable", target["username"])
            st.rerun()


def _backup(eng):
    st.subheader("Download a backup")
    st.write("One zip file with every member, gift, pledge, attendance record, group, event, child and the audit log. "
             "User logins are **not** included (so the file holds no passwords).")
    st.warning("The backup holds personal and financial details. Store it somewhere private, "
               "e.g. a church Google Drive folder only leaders can open.")
    stamp = ui.now().strftime("%Y-%m-%d_%H%M")
    if st.download_button("Download backup (.zip)", db.export_backup(eng), file_name=f"church_backup_{stamp}.zip",
                          mime="application/zip", type="primary"):
        ui.audit("backup.download")
    last = db.list_audit(eng, limit=1000)
    last = last[last["action"] == "backup.download"]
    st.caption(f"Last backup downloaded: {last.iloc[0]['at']} by {last.iloc[0]['username']}" if len(last)
               else "No backup has been downloaded yet.")

    st.subheader("Restore from a backup")
    if not db.is_empty(eng):
        st.info("Restore only works on an empty database (for example, after moving to a new host), "
                "so it can never overwrite or mix up existing records. This database already has data.")
        return
    upload = st.file_uploader("Backup zip", type="zip")
    if upload and st.button("Restore now"):
        try:
            counts = db.restore_backup(eng, upload.getvalue())
            ui.audit("backup.restore", ", ".join(f"{k}={v}" for k, v in counts.items()))
            st.success("Restored: " + ", ".join(f"{v} {k}" for k, v in counts.items() if v))
        except Exception as err:  # bad or foreign file: show the reason, keep the app running
            st.error(f"Restore failed and nothing was changed: {err}")
