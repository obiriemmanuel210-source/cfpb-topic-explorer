from datetime import date

import pandas as pd
import plotly.express as px
import streamlit as st

import db
import receipts
import ui


def render():
    eng = ui.engine()
    st.title("💰 Giving")
    tab_add, tab_report, tab_pledges, tab_statements = st.tabs(["Record giving", "Reports", "Pledges", "Statements"])
    options = ui.member_options()

    with tab_add:
        givers = {0: "Anonymous / loose offering", **options}
        with st.form("donation", clear_on_submit=True):
            c1, c2, c3 = st.columns(3)
            giver = c1.selectbox("Giver", list(givers), format_func=givers.get)
            amount = c2.number_input(f"Amount ({ui.CURRENCY.strip()})", min_value=0.0, step=1.0, format="%.2f")
            gift_date = c3.date_input("Date", ui.today())
            c1, c2 = st.columns(2)
            fund = c1.selectbox("Fund", db.GIVING_FUNDS)
            method = c2.selectbox("Method", db.PAYMENT_METHODS)
            notes = st.text_input("Notes / reference", placeholder="e.g. MoMo transaction ID")
            if st.form_submit_button("Save", type="primary"):
                try:
                    gid = db.add_donation(eng, gift_date, amount, fund, giver or None, method, notes, ui.username())
                    ui.audit("giving.add", f"#{gid} {gift_date} {givers[giver]} {ui.money(amount)} {fund}")
                    st.success(f"Recorded {ui.money(amount)} to {fund}.")
                except ValueError as err:
                    st.error(str(err))

    with tab_report:
        _reports(eng)

    with tab_pledges:
        _pledges(eng, options)

    with tab_statements:
        _statements(eng, options)


def _reports(eng):
    c1, c2 = st.columns(2)
    start = c1.date_input("From", ui.today().replace(day=1), key="giv_from")
    end = c2.date_input("To", ui.today(), key="giv_to")
    gifts = db.list_donations(eng, start, end)
    if gifts.empty:
        st.info("No giving in this range.")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Total", ui.money(gifts["amount"].sum()))
    c2.metric("Gifts", len(gifts))
    c3.metric("Named givers", gifts["member_id"].nunique())

    left, right = st.columns(2)
    by_fund = gifts.groupby("fund", as_index=False)["amount"].sum().sort_values("amount", ascending=False)
    left.dataframe(by_fund, hide_index=True, width="stretch")
    by_method = gifts.groupby("method", as_index=False)["amount"].sum().sort_values("amount", ascending=False)
    left.dataframe(by_method, hide_index=True, width="stretch")
    by_week = gifts.assign(week=pd.to_datetime(gifts["donation_date"]).dt.to_period("W").dt.start_time)
    by_week = by_week.groupby(["week", "fund"], as_index=False)["amount"].sum()
    right.plotly_chart(px.bar(by_week, x="week", y="amount", color="fund", labels={"week": "Week of", "amount": ""}),
                       width="stretch")

    st.dataframe(gifts.drop(columns=["member_id"]), hide_index=True, width="stretch")
    ui.download_button(gifts, f"giving_{start}_{end}.csv")

    with st.expander("Delete an entry (for corrections)"):
        indexed = gifts.set_index("id")
        gift_id = st.selectbox("Entry", gifts["id"], format_func=lambda i: (
            f"#{i} · {indexed.loc[i, 'donation_date']} · {indexed.loc[i, 'giver']} · "
            f"{ui.money(indexed.loc[i, 'amount'])} · {indexed.loc[i, 'fund']}"))
        if ui.confirm_button("Delete entry", "del_gift", "Deleting is recorded in the audit log with your name."):
            row = indexed.loc[gift_id]
            db.delete_donation(eng, int(gift_id))
            ui.audit("giving.delete", f"#{gift_id} {row['donation_date']} {row['giver']} {ui.money(row['amount'])} {row['fund']}")
            st.rerun()


def _pledges(eng, options):
    st.caption("A pledge is a promise to give an amount to a fund by a date. Progress counts that member's "
               "gifts to the same fund between the start and end dates.")
    with st.form("pledge", clear_on_submit=True):
        c1, c2, c3 = st.columns(3)
        member_id = c1.selectbox("Member", list(options), format_func=options.get, index=None)
        fund = c2.selectbox("Fund", db.GIVING_FUNDS, index=db.GIVING_FUNDS.index("Building fund"))
        amount = c3.number_input(f"Pledged amount ({ui.CURRENCY.strip()})", min_value=0.0, step=10.0, format="%.2f")
        c1, c2 = st.columns(2)
        start = c1.date_input("From", ui.today().replace(month=1, day=1), key="pl_from")
        end = c2.date_input("To", ui.today().replace(month=12, day=31), key="pl_to")
        notes = st.text_input("Notes")
        if st.form_submit_button("Add pledge", type="primary"):
            if member_id is None:
                st.error("Choose a member.")
            else:
                try:
                    db.add_pledge(eng, member_id, fund, amount, start, end, notes)
                    ui.audit("pledge.add", f"{options[member_id]} {ui.money(amount)} {fund}")
                    st.success("Pledge added.")
                except ValueError as err:
                    st.error(str(err))

    pl = db.list_pledges(eng)
    if pl.empty:
        st.info("No pledges yet.")
        return
    c1, c2, c3 = st.columns(3)
    c1.metric("Total pledged", ui.money(pl["pledged"].sum()))
    c2.metric("Given towards pledges", ui.money(pl["given"].clip(upper=pl["pledged"]).sum()))
    c3.metric("Outstanding", ui.money(pl["remaining"].sum()))
    st.dataframe(
        pl[["member", "fund", "pledged", "given", "remaining", "progress_pct", "start_date", "end_date"]],
        hide_index=True, width="stretch",
        column_config={"progress_pct": st.column_config.ProgressColumn("Progress", min_value=0, max_value=100, format="%d%%")},
    )
    ui.download_button(pl, "pledges.csv", key="dl_pledges")
    with st.expander("Delete a pledge"):
        pid = st.selectbox("Pledge", pl["id"], format_func=lambda i: (
            lambda r: f"{r['member']} · {r['fund']} · {ui.money(r['pledged'])}")(pl.set_index("id").loc[i]))
        if ui.confirm_button("Delete pledge", "del_pledge", "Only the pledge is deleted; gifts stay."):
            db.delete_pledge(eng, int(pid))
            ui.audit("pledge.delete", f"#{pid}")
            st.rerun()


def _statement_pdf(eng, member_id, start, end):
    member = db.get_member(eng, member_id)
    gifts = db.list_donations(eng, start, end, member_id=member_id)
    pdf = receipts.giving_statement(member, gifts, start, end, ui.CHURCH_NAME, ui.CURRENCY,
                                    ui.setting("church_details", ""), ui.setting("statement_signatory", ""))
    return member, gifts, pdf


def _statements(eng, options):
    st.caption("PDF statements of giving for members — for their records, tax or employer requirements.")
    c1, c2 = st.columns(2)
    year = ui.today().year
    start = c1.date_input("From", date(year, 1, 1), key="st_from")
    end = c2.date_input("To", ui.today(), key="st_to")

    st.subheader("One member")
    member_id = st.selectbox("Member", list(options), format_func=options.get, index=None, key="st_member")
    if member_id is not None:
        member, gifts, pdf = _statement_pdf(eng, member_id, start, end)
        st.write(f"{len(gifts)} gifts, total {ui.money(gifts['amount'].sum())}")
        name = f"{member['first_name']}_{member['last_name']}_{start}_{end}.pdf".replace(" ", "_")
        st.download_button("Download PDF statement", pdf, file_name=name, mime="application/pdf")

    st.subheader("Everyone who gave in this period")
    if st.button("Prepare all statements"):
        givers = db.list_donations(eng, start, end)["member_id"].dropna().astype(int).unique()
        items = []
        for mid in givers:
            member, _, pdf = _statement_pdf(eng, int(mid), start, end)
            items.append((f"{member['last_name']}_{member['first_name']}_{mid}.pdf".replace(" ", "_"), pdf))
        if not items:
            st.info("No named givers in this period.")
        else:
            ui.audit("giving.statements", f"{len(items)} statements {start} to {end}")
            st.download_button(f"Download {len(items)} statements (zip)", receipts.statements_zip(items),
                               file_name=f"statements_{start}_{end}.zip", mime="application/zip")
