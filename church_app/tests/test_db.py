import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import db  # noqa: E402


@pytest.fixture
def conn():
    return db.connect(":memory:")


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
