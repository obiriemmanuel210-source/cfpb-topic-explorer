# Church Manager

> This app is moving to its own repository, `church-manager`. This folder is a copy kept until that move is done.

A church management app built with Streamlit. It runs on a local SQLite file, or on a hosted Postgres database (such as Supabase) for real use.

## Features

| Page | What it does | Who can open it |
|---|---|---|
| Dashboard | Member count, average Sunday attendance, giving this month, charts, birthdays in the next 30 days, upcoming events, members not seen in 4 weeks | admin, finance, pastoral (giving numbers only for admin/finance) |
| Members | Search, add, edit, remove; CSV export | admin, pastoral (finance can view only) |
| Groups | Cells, ministries, departments; leaders, meeting times, member lists | admin, pastoral |
| Attendance | Service headcount plus named check-ins; history chart | admin, pastoral |
| Giving | Record gifts (named or anonymous), reports, **pledges with progress**, **PDF giving statements** (one member or everyone at once) | admin, finance |
| Children | Register children with guardian and allergy notes, **check-in with a 4-character pickup code**, check-out only with the matching code, history | admin, pastoral, children's volunteers |
| Events | Add and list events | admin, pastoral |
| Messages | Personalised messages for everyone, a group, birthdays, absentees or pledge reminders; **send by SMS through mNotify**, one-tap WhatsApp links, or CSV | admin, pastoral, finance (pledge reminders: admin/finance) |
| Admin | User accounts and roles, **backup download and restore**, **audit log** of every change | admin |

Security: each person has their own login. Passwords are stored as salted hashes, never as plain text. A username is locked for 15 minutes after 5 wrong passwords, and every change is written to the audit log with who did it.

## Run it on your computer

```bash
pip install -r church_app/requirements.txt
streamlit run church_app/app.py
```

On first launch the app asks you to create the admin account. Data is saved to `data/church.db`, which is never committed to git.

## Put it online (recommended setup)

Streamlit Community Cloud wipes its disk whenever the app restarts, so a SQLite file there **will lose your data**. Keep the data in Supabase (hosted Postgres) instead:

1. Create a free project at supabase.com and pick the region closest to you. Save the database password.
2. In Supabase, click **Connect** and copy the **Session pooler** connection string. Replace `[YOUR-PASSWORD]` in it.
3. On share.streamlit.io, deploy this repo with main file `app.py`.
4. In the app's **Settings → Secrets**, paste the contents of `.streamlit/secrets.toml.example` with your values, including `database_url` and a long random `setup_key`.
5. Open the app, enter the setup key, and create your admin account. Then add the other users on the Admin page.

The tables are created automatically on first run.

Moving from a local SQLite file to Supabase: on the old copy, go to Admin → Backup and download the zip. Then on the new, empty copy, use Admin → Restore.

## Settings

All of these are optional. Set them in `secrets.toml` or as upper-case environment variables.

| Setting | Default | Purpose |
|---|---|---|
| `church_name` | Our Church | Header, sidebar, messages, statements |
| `currency` | `$` | e.g. `"GH₵ "` |
| `timezone` | Africa/Accra | Dates and check-in times (servers run on UTC) |
| `phone_country_code` | 233 | Turns `024…` into `23324…` for WhatsApp links |
| `setup_key` | none | Required to create the first admin. **Set it before going online.** |
| `database_url` | local SQLite | Postgres connection string |
| `church_details`, `statement_signatory` | blank | Printed on PDF statements |
| `mnotify_api_key` | none | Turns on SMS sending (mNotify dashboard → API) |
| `sms_sender_id` | none | Approved sender name, max 11 characters, e.g. `GRACECHAPEL` |

## Tests

```bash
python -m pytest tests
# also against a throwaway Postgres database:
TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/church_test python -m pytest tests
```

## Known limits

- **Backups are manual.** An admin must download the backup zip regularly (weekly is a good habit). Supabase's free plan has no automatic daily backups, and it pauses projects after about a week with no activity. Opening the app wakes the project, but the first load is slow.
- **Restore only works into an empty database.** This is deliberate, so a restore can never mix or overwrite records.
- **No member self-service.** Members can't log in to update their own details or see their giving.
- **Group attendance isn't tracked separately** from service attendance.

## Setting up SMS (mNotify)

1. Sign up at mnotify.com and buy SMS credit.
2. In the mNotify dashboard, register a **sender ID** (the name people see, max 11 characters, e.g. `GRACECHAPEL`) and wait for approval.
3. Generate an **API key** in the dashboard.
4. Add `mnotify_api_key` and `sms_sender_id` to the app's secrets.
5. On the Messages page, choose who to message, check the balance, tick the confirmation box and press **Send SMS**.

How it sends: mNotify's quick-SMS endpoint sends one text to many numbers. People who get exactly the same text are sent together, and each personalised text (e.g. "Dear Ama…") is its own request. If mNotify returns an error (wrong key, empty wallet), sending stops at once and the page says how many messages went and how many didn't. Every send is recorded in the audit log.

Each SMS holds 160 plain characters. Special characters such as ɛ, ɔ or ₵ cut that to 70, so those messages use more credit. The page shows an estimate before you send.
