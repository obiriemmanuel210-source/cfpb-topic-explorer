import pytest

import sms


class FakeResponse:
    def __init__(self, data, status=200):
        self.data, self.status_code = data, status

    def json(self):
        if self.data is None:
            raise ValueError("not json")
        return self.data


class FakeMnotify:
    """Records requests and answers like mNotify's documented responses."""

    def __init__(self, fail_on_call=None, reply=None):
        self.calls, self.fail_on_call, self.reply = [], fail_on_call, reply

    def post(self, url, params, json):
        self.calls.append((url, params, json))
        if self.fail_on_call == len(self.calls):
            return FakeResponse(self.reply or {"status": "error", "code": "1002", "message": "Insufficient balance"})
        n = len(json["recipient"])
        return FakeResponse({"status": "success", "code": "2000", "message": "messages sent successfully",
                             "summary": {"total_sent": n, "total_rejected": 0, "numbers_sent": json["recipient"],
                                         "credit_used": n, "credit_left": 100 - n}})

    def get(self, url, params):
        return FakeResponse({"status": "success", "balance": 1000, "bonus": 5})


def test_to_local_and_parts():
    assert sms.to_local("233241234567") == "0241234567"
    assert sms.to_local("447700900123") == "447700900123"
    assert sms.parts("a" * 160) == 1 and sms.parts("a" * 161) == 2
    assert sms.parts("ɛ" * 70) == 1 and sms.parts("ɛ" * 71) == 2


def test_groups_identical_messages_into_one_request():
    fake = FakeMnotify()
    rows = [{"phone": "233241111111", "message": "Service at 9am"},
            {"phone": "233242222222", "message": "Service at 9am"},
            {"phone": "233243333333", "message": "Dear Ama, happy birthday"},
            {"phone": "", "message": "no phone, skipped"}]
    result = sms.send_personalised("KEY", "GRACE", rows, http_post=fake.post)
    assert result["sent"] == 3 and result["requests"] == 2 and result["error"] is None
    url, params, body = fake.calls[0]
    assert url.endswith("/sms/quick") and params == {"key": "KEY"}
    assert body["recipient"] == ["0241111111", "0242222222"] and body["sender"] == "GRACE"
    assert body["is_schedule"] is False


def test_stops_at_first_error_and_reports_what_did_not_go():
    fake = FakeMnotify(fail_on_call=2)
    rows = [{"phone": f"23324{i:07d}", "message": f"Dear person {i}"} for i in range(4)]
    result = sms.send_personalised("KEY", "GRACE", rows, http_post=fake.post)
    assert result["sent"] == 1 and len(fake.calls) == 2
    assert "Insufficient balance" in result["error"]
    assert result["failed"] == 1 and result["not_attempted"] == 2


def test_bad_sender_and_non_json_reply():
    with pytest.raises(sms.SmsError):
        sms.send_quick("KEY", "THIS_IS_TOO_LONG", ["024"], "hi")
    with pytest.raises(sms.SmsError):
        sms.send_quick("KEY", "GRACE", ["024"], "hi", http_post=lambda *a: FakeResponse(None, 502))


def test_balance():
    assert sms.balance("KEY", http_get=FakeMnotify().get) == (1000, 5)
    with pytest.raises(sms.SmsError):
        sms.balance("BAD", http_get=lambda *a: FakeResponse({"status": "error", "message": "Invalid API key"}))
