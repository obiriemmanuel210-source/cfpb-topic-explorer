# Church Manager

A simple church management app built with Streamlit and SQLite.

## Features

- **Dashboard**: member count, average Sunday attendance, giving this month, attendance trend chart, giving-by-fund chart, upcoming birthdays (next 30 days), upcoming events, and a follow-up list of members not seen in 4 weeks.
- **Members**: searchable directory, add / edit / remove, status (Member, Regular attendee, Visitor, Inactive), ministry/group, CSV export, and a per-member giving statement.
- **Attendance**: record each service with a total headcount plus named check-ins; history chart and CSV export.
- **Giving**: record tithes, offerings and other funds (named or anonymous, with payment method); reports by date range, by fund and by week; CSV export; delete wrong entries.
- **Events**: add, list and delete church events.

## Run it locally

```bash
pip install -r church_app/requirements.txt
streamlit run church_app/app.py
```

Data is saved to `church_app/data/church.db` (created on first run, not committed to git).

## Settings

Copy `church_app/.streamlit/secrets.toml.example` to `church_app/.streamlit/secrets.toml` and set:

| Setting | What it does |
|---|---|
| `church_name` | Name shown in the header and sidebar |
| `currency` | Currency symbol for giving (default `$`) |
| `app_password` | Shared password to open the app. **If not set, anyone with the link can see everything.** |
| `db_path` | Where to keep the SQLite file |

Each can also be set as an environment variable in upper case (e.g. `APP_PASSWORD`).

## Tests

```bash
cd church_app && python -m pytest tests
```

## Known limits (read before using with real data)

- **Hosting on Streamlit Community Cloud will lose data.** Its disk is wiped when the app restarts or redeploys, so the SQLite file does not survive. It is fine for a demo. For real use, run it on a computer/server you control, or move the database to a hosted one (e.g. Supabase/Postgres).
- **One shared password, no user roles.** Everyone who signs in can see and change everything, including giving records. Fine for a small admin team; not for giving members their own logins.
- **No backups built in.** Copy `data/church.db` somewhere safe regularly.
- **No SMS / email sending yet.** The follow-up and birthday lists show phone numbers but do not send messages.
