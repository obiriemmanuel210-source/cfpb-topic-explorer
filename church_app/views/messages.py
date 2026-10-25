import re
from datetime import timedelta
from urllib.parse import quote

import pandas as pd
import streamlit as st

import auth
import db
import ui

TEMPLATES = {
    "Everyone (active members)": "Dear {first_name}, ",
    "A group": "Hello {first_name}, ",
    "Birthdays in the next 7 days": "Happy birthday {first_name}! The {church} family is thanking God for you. Have a blessed day.",
    "Not seen in 4 weeks": "Dear {first_name}, we have missed you at {church}. We hope all is well — is there anything we can pray with you about?",
    "Pledge reminders": "Dear {first_name}, thank you for your pledge to the {fund}. So far you have given {given} of {pledged}. God bless you.",
}


def normalise_phone(phone, country_code):
    """Turn local numbers like 024 123 4567 into international 233241234567 form."""
    digits = re.sub(r"\D", "", phone or "")
    if not digits:
        return ""
    if (phone or "").strip().startswith("+") or digits.startswith(country_code):
        return digits
    if digits.startswith("00"):
        return digits[2:]
    if digits.startswith("0"):
        return country_code + digits[1:]
    return digits


def audience(eng, kind, group_id=None):
    today = ui.today()
    if kind == "Everyone (active members)":
        df = db.list_members(eng)
        return df[df["status"].isin(["Member", "Regular attendee"])][["first_name", "last_name", "phone"]]
    if kind == "A group":
        return db.list_group_members(eng, group_id)[["first_name", "last_name", "phone"]]
    if kind == "Birthdays in the next 7 days":
        b = db.upcoming_birthdays(eng, today, days=7)
        return pd.DataFrame({"first_name": b["first_name"], "last_name": b["name"].str.split(" ", n=1).str[1],
                             "phone": b["phone"]})
    if kind == "Not seen in 4 weeks":
        return db.absent_members(eng, since=today - timedelta(weeks=4))[["first_name", "last_name", "phone"]]
    if kind == "Pledge reminders":
        pl = db.list_pledges(eng)
        pl = pl[(pl["remaining"] > 0) & (pl["end_date"] >= today.isoformat())]
        return pd.DataFrame({
            "first_name": pl["first_name"], "last_name": pl["member"].str.split(" ", n=1).str[1], "phone": pl["phone"],
            "fund": pl["fund"], "given": pl["given"].map(ui.money), "pledged": pl["pledged"].map(ui.money),
            "remaining": pl["remaining"].map(ui.money)})
    return pd.DataFrame(columns=["first_name", "last_name", "phone"])


def render():
    eng = ui.engine()
    role = ui.user()["role"]
    st.title("✉️ Messages")
    st.caption("Prepare personalised messages, then send them by WhatsApp (one tap each) or upload the CSV "
               "to your bulk-SMS provider. This app does not send SMS by itself yet.")

    kinds = [k for k in TEMPLATES if k != "Pledge reminders" or auth.sees_giving(role)]
    kind = st.selectbox("Who is this for?", kinds)
    group_id = None
    if kind == "A group":
        groups = db.list_groups(eng)
        if groups.empty:
            st.info("No groups yet.")
            return
        labels = dict(zip(groups["id"].astype(int), groups["name"]))
        group_id = st.selectbox("Group", list(labels), format_func=labels.get)

    people = audience(eng, kind, group_id)
    fields = ["{first_name}", "{last_name}", "{church}"] + [f"{{{c}}}" for c in ("fund", "given", "pledged", "remaining")
                                                         if c in people.columns]
    message = st.text_area("Message", TEMPLATES[kind], key=f"msg_{kind}", height=110,
                           help="These words are replaced for each person: " + ", ".join(fields))
    unicode_text = any(ord(ch) > 127 for ch in message)
    per_sms = 70 if unicode_text else 160
    st.caption(f"{len(message)} characters ≈ {max(1, -(-len(message) // per_sms))} SMS each"
               + (" (contains special characters, so each SMS holds only 70)" if unicode_text else ""))

    if people.empty:
        st.info("Nobody matches this list right now.")
        return

    country = str(ui.setting("phone_country_code", "233"))
    rows = []
    for p in people.fillna("").to_dict("records"):
        values = {**p, "church": ui.CHURCH_NAME}
        try:
            text = message.format(**values)
        except (KeyError, IndexError, ValueError) as err:
            st.error(f"The message has a placeholder this list doesn't support: {err}. Use only {', '.join(fields)}.")
            return
        number = normalise_phone(p["phone"], country)
        rows.append({"name": f"{p['first_name']} {p['last_name']}", "phone": number, "message": text,
                     "whatsapp": f"https://wa.me/{number}?text={quote(text)}" if number else None})
    out = pd.DataFrame(rows)
    missing = out[out["phone"] == ""]
    out = out[out["phone"] != ""]

    st.write(f"**{len(out)}** people with a phone number" + (f" · {len(missing)} without" if len(missing) else ""))
    st.dataframe(out, hide_index=True, width="stretch",
                 column_config={"whatsapp": st.column_config.LinkColumn("WhatsApp", display_text="Open chat")})
    if st.download_button("Download CSV for bulk SMS", out[["name", "phone", "message"]].to_csv(index=False).encode(),
                          file_name="messages.csv", mime="text/csv"):
        ui.audit("messages.export", f"{kind}: {len(out)} recipients")
    if len(missing):
        with st.expander("People with no phone number"):
            st.dataframe(missing[["name"]], hide_index=True)
