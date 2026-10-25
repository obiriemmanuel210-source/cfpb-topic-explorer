from datetime import date, datetime, timedelta

import pytest

import auth
import db
import receipts


def test_add_and_search_members(conn):
    db.add_member(conn, first_name="Ama", last_name="Mensah", phone="0244000000")
    db.add_member(conn, first_name="Kofi", last_name="Boateng", status="Visitor")
    assert len(db.list_members(conn)) == 2
    assert db.list_members(conn, search="ama")["first_name"].tolist() == ["Ama"]
    assert db.list_members(conn, status="Visitor")["first_name"].tolist() == ["Kofi"]


def test_member_requires_name(conn):
    with pytest.raises(ValueError):
        db.add_member(conn, first_name="", last_name="X")


def test_update_member(conn):
    mid = db.add_member(conn, first_name="Ama", last_name="Mensah")
    db.update_member(conn, mid, phone="123", birth_date=date(1990, 5, 1))
    m = db.get_member(conn, mid)
    assert m["phone"] == "123" and m["birth_date"] == "1990-05-01"


def test_record_service_is_upsert_and_headcount_floor(conn):
    a = db.add_member(conn, first_name="A", last_name="A")
    b = db.add_member(conn, first_name="B", last_name="B")
    d = date(2026, 10, 18)
    db.record_service(conn, d, "Sunday service", headcount=1, member_ids=[a, b, a])
    s = db.get_service(conn, d, "Sunday service")
    assert s["headcount"] == 2 and sorted(s["member_ids"]) == [a, b]
    db.record_service(conn, d, "Sunday service", headcount=50, member_ids=[a])
    assert len(db.list_services(conn)) == 1
    s = db.get_service(conn, d, "Sunday service")
    assert s["headcount"] == 50 and s["member_ids"] == [a]


def test_absent_members_needs_enough_data(conn):
    a = db.add_member(conn, first_name="Here", last_name="A")
    db.add_member(conn, first_name="Gone", last_name="B")
    today = date(2026, 10, 19)
    db.record_service(conn, today - timedelta(days=7), "Sunday service", member_ids=[a])
    assert db.absent_members(conn, today - timedelta(weeks=4)).empty
    db.record_service(conn, today - timedelta(days=14), "Sunday service", member_ids=[a])
    db.record_service(conn, today - timedelta(days=21), "Sunday service", member_ids=[a])
    assert db.absent_members(conn, today - timedelta(weeks=4))["first_name"].tolist() == ["Gone"]


def test_donations_and_member_delete_keeps_gift(conn):
    mid = db.add_member(conn, first_name="Ama", last_name="Mensah")
    db.add_donation(conn, date(2026, 10, 1), 100, "Tithe", mid)
    db.add_donation(conn, date(2026, 10, 2), 20, "Offering")
    with pytest.raises(ValueError):
        db.add_donation(conn, date(2026, 10, 2), 0, "Offering")
    gifts = db.list_donations(conn, start=date(2026, 10, 1), end=date(2026, 10, 31))
    assert gifts["amount"].sum() == 120
    db.delete_member(conn, mid)
    gifts = db.list_donations(conn)
    assert len(gifts) == 2 and set(gifts["giver"]) == {"Anonymous"}


def test_upcoming_birthdays_wraps_year_and_leap_day(conn):
    db.add_member(conn, first_name="Jan", last_name="X", birth_date="1990-01-05")
    db.add_member(conn, first_name="Leap", last_name="Y", birth_date="2000-02-29")
    db.add_member(conn, first_name="Far", last_name="Z", birth_date="1990-06-01")
    b = db.upcoming_birthdays(conn, date(2026, 12, 20), days=30)
    assert b["name"].tolist() == ["Jan X"]
    b = db.upcoming_birthdays(conn, date(2027, 2, 20), days=30)
    assert b["name"].tolist() == ["Leap Y"]


def test_events(conn):
    db.add_event(conn, "Harvest", date(2026, 11, 1))
    db.add_event(conn, "Old", date(2020, 1, 1))
    assert db.list_events(conn, start=date(2026, 10, 19))["title"].tolist() == ["Harvest"]
    with pytest.raises(ValueError):
        db.add_event(conn, "  ", date(2026, 11, 1))


def test_search_is_case_insensitive(conn):
    db.add_member(conn, first_name="Abena", last_name="Owusu", email="Abena@Example.com")
    assert len(db.list_members(conn, search="ABENA")) == 1
    assert len(db.list_members(conn, search="example.COM")) == 1


def test_groups(conn):
    a = db.add_member(conn, first_name="A", last_name="A")
    b = db.add_member(conn, first_name="B", last_name="B")
    g = db.add_group(conn, "Choir", "Ministry", leader_id=a)
    with pytest.raises(ValueError):
        db.add_group(conn, "choir")
    db.set_group_members(conn, g, [a, b, b])
    assert sorted(db.group_member_ids(conn, g)) == [a, b]
    row = db.list_groups(conn).iloc[0]
    assert row["members"] == 2 and row["leader"] == "A A"
    assert db.member_groups(conn, b)["name"].tolist() == ["Choir"]
    db.delete_member(conn, b)
    assert db.group_member_ids(conn, g) == [a]
    db.delete_group(conn, g)
    assert db.list_groups(conn).empty and len(db.list_members(conn)) == 1


def test_pledge_progress_counts_only_matching_gifts(conn):
    m = db.add_member(conn, first_name="Ama", last_name="Mensah")
    other = db.add_member(conn, first_name="Kofi", last_name="B")
    db.add_pledge(conn, m, "Building fund", 1000, date(2026, 1, 1), date(2026, 12, 31))
    db.add_donation(conn, date(2026, 3, 1), 300, "Building fund", m)
    db.add_donation(conn, date(2026, 4, 1), 50, "Tithe", m)            # wrong fund
    db.add_donation(conn, date(2025, 12, 31), 99, "Building fund", m)  # before pledge
    db.add_donation(conn, date(2026, 5, 1), 70, "Building fund", other)  # someone else
    p = db.list_pledges(conn).iloc[0]
    assert (p["given"], p["remaining"], p["progress_pct"]) == (300, 700, 30)
    with pytest.raises(ValueError):
        db.add_pledge(conn, m, "Missions", 10, date(2026, 5, 1), date(2026, 1, 1))


def test_child_checkin_and_checkout(conn):
    parent = db.add_member(conn, first_name="Efua", last_name="Asante", phone="0201112222")
    with pytest.raises(ValueError):
        db.add_child(conn, first_name="No", last_name="Guardian")
    k1 = db.add_child(conn, first_name="Kwame", last_name="Asante", class_name="Beginners (3-5)", guardian_id=parent)
    k2 = db.add_child(conn, first_name="Esi", last_name="Asante", guardian_id=parent)
    day, at = date(2026, 10, 25), datetime(2026, 10, 25, 9, 0)
    code = db.check_in_child(conn, k1, day, at, "vol")
    assert len(code) == 4 and db.check_in_child(conn, k1, day, at) == code  # no double check-in
    assert db.check_in_child(conn, k2, day, at, code=code) == code          # sibling shares code
    rows = db.list_checkins(conn, on_date=day)
    assert len(rows) == 2 and set(rows["guardian_phone"]) == {"0201112222"}
    first = int(rows[rows["child_id"] == k1]["id"].iloc[0])
    with pytest.raises(ValueError):
        db.check_out_child(conn, first, code, at, "")
    assert db.check_out_child(conn, first, "ZZZZ", at, "Efua") is False
    assert db.check_out_child(conn, first, code.lower(), at, "Efua") is True
    assert db.check_out_child(conn, first, code, at, "Efua") is False  # already out


def test_users_and_passwords(conn):
    assert db.count_users(conn) == 0
    db.add_user(conn, " Admin ", auth.hash_password("correct horse"), "admin")
    with pytest.raises(ValueError):
        db.add_user(conn, "admin", "x", "admin")
    u = db.get_user(conn, username="ADMIN")
    assert u["username"] == "admin" and auth.verify_password("correct horse", u["password_hash"])
    assert not auth.verify_password("wrong", u["password_hash"])
    assert not auth.verify_password("x", "garbage")
    db.update_user(conn, u["id"], active=0)
    assert db.get_user(conn, user_id=u["id"])["active"] == 0


def test_failed_login_counter(conn):
    now = datetime(2026, 10, 25, 10, 0)
    for minutes in (1, 2, 30):
        db.log(conn, "ama", "login.failed", at=now - timedelta(minutes=minutes))
    db.log(conn, "kofi", "login.failed", at=now)
    assert db.count_actions(conn, "login.failed", "ama", now - timedelta(minutes=15)) == 2


def test_password_rules():
    assert auth.password_problem("short")
    assert auth.password_problem("password")
    assert auth.password_problem("a good long one") is None


def test_roles():
    assert auth.can("finance", "Giving") and not auth.can("pastoral", "Giving")
    assert auth.can("children", "Children") and not auth.can("children", "Members")
    assert all(auth.can("admin", p) for p in auth.PAGE_ACCESS)


def test_backup_restore_roundtrip(conn):
    m = db.add_member(conn, first_name="Ɔboɔ", last_name="Nkansah", birth_date=date(1990, 1, 2))
    g = db.add_group(conn, "Ushers")
    db.set_group_members(conn, g, [m])
    db.record_service(conn, date(2026, 10, 18), "Sunday service", 40, member_ids=[m])
    db.add_donation(conn, date(2026, 10, 18), 12.5, "Tithe", m)
    db.add_pledge(conn, m, "Missions", 100, date(2026, 1, 1), date(2026, 12, 31))
    k = db.add_child(conn, first_name="Yaw", last_name="N", guardian_id=m)
    db.check_in_child(conn, k, date(2026, 10, 18), datetime(2026, 10, 18, 9))
    db.add_user(conn, "admin", auth.hash_password("correct horse"), "admin")
    backup = db.export_backup(conn)

    with pytest.raises(ValueError):  # refuses to restore over existing data
        db.restore_backup(conn, backup)

    fresh = db.connect(":memory:")
    counts = db.restore_backup(fresh, backup)
    assert counts["members"] == 1 and counts["donations"] == 1 and counts["child_checkins"] == 1
    assert db.list_members(fresh)["first_name"].tolist() == ["Ɔboɔ"]
    assert db.list_pledges(fresh).iloc[0]["given"] == 0  # gift was to a different fund
    assert db.list_donations(fresh)["amount"].sum() == 12.5
    assert db.count_users(fresh) == 0  # logins are never in backups
    # new rows get fresh ids after a restore
    assert db.add_member(fresh, first_name="New", last_name="Person") == m + 1


def test_restore_rejects_foreign_zip():
    import io
    import zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("hello.txt", "hi")
    with pytest.raises(ValueError):
        db.restore_backup(db.connect(":memory:"), buf.getvalue())


def test_statement_pdf_handles_ghanaian_names_and_cedi(conn):
    m = db.add_member(conn, first_name="Ɛsi", last_name="Ɔforiwaa", address="Kumasi")
    db.add_donation(conn, date(2026, 2, 1), 150, "Tithe", m, "Mobile money")
    db.add_donation(conn, date(2026, 3, 1), 50, "Missions", m, "Cash")
    pdf = receipts.giving_statement(db.get_member(conn, m), db.list_donations(conn, member_id=m),
                                    date(2026, 1, 1), date(2026, 12, 31), "Grace Chapel", "GH₵ ", "Box 1, Accra", "Treasurer")
    assert pdf.startswith(b"%PDF") and len(pdf) > 1000
    assert receipts.statements_zip([("a.pdf", pdf)]).startswith(b"PK")
