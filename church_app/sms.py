"""Sending SMS through mNotify (BMS API v2, https://developer.bms.africa/).

The quick-SMS endpoint sends one text to many numbers, so personalised
messages are grouped: everyone who gets exactly the same text goes in one
request, and each different text is its own request.
"""

from collections import defaultdict

import requests

BASE_URL = "https://api.mnotify.com/api"
MAX_SENDER_LENGTH = 11
BATCH_SIZE = 500  # keep each request a sensible size


class SmsError(Exception):
    pass


def _http_post(url, params, json):
    return requests.post(url, params=params, json=json, timeout=30)


def _http_get(url, params):
    return requests.get(url, params=params, timeout=30)


def to_local(number, country_code="233"):
    """mNotify's examples use local numbers (0241234567), so convert 233241234567 back to that."""
    number = str(number)
    if country_code and number.startswith(country_code) and len(number) == len(country_code) + 9:
        return "0" + number[len(country_code):]
    return number


def parts(text):
    """How many SMS a text needs. Any non-basic character (e.g. ɛ, ₵, emoji) cuts each SMS to 70."""
    unicode_text = any(ord(ch) > 127 for ch in text)
    single, multi = (70, 67) if unicode_text else (160, 153)
    return 1 if len(text) <= single else -(-len(text) // multi)


def _json(response):
    try:
        return response.json()
    except ValueError:
        raise SmsError(f"mNotify replied with something unexpected (HTTP {response.status_code}).")


def check_sender(sender):
    if not sender or len(sender) > MAX_SENDER_LENGTH:
        raise SmsError(f"Sender ID must be 1-{MAX_SENDER_LENGTH} characters and registered with mNotify.")


def balance(api_key, http_get=_http_get):
    """Return (balance, bonus) SMS credits."""
    data = _json(http_get(f"{BASE_URL}/balance/sms", {"key": api_key}))
    if data.get("status") != "success":
        raise SmsError(data.get("message") or "Could not read the SMS balance. Check the API key.")
    return data.get("balance", 0), data.get("bonus", 0)


def send_quick(api_key, sender, recipients, message, http_post=_http_post):
    """Send one message to a list of numbers. Returns mNotify's summary dict."""
    check_sender(sender)
    if not recipients:
        return {"total_sent": 0, "total_rejected": 0, "credit_used": 0}
    data = _json(http_post(f"{BASE_URL}/sms/quick", {"key": api_key}, {
        "recipient": list(recipients),
        "sender": sender,
        "message": message,
        "is_schedule": False,
        "schedule_date": "",
    }))
    if data.get("status") != "success":
        raise SmsError(data.get("message") or f"mNotify refused the message (code {data.get('code')}).")
    return data.get("summary") or {}


def send_personalised(api_key, sender, rows, country_code="233", http_post=_http_post, on_progress=None):
    """Send each row's own message to its phone.

    `rows` is a list of {"phone": ..., "message": ...}. Stops at the first
    error so a bad key or empty wallet doesn't produce a flood of failures;
    the result says how far it got.
    """
    by_text = defaultdict(list)
    for r in rows:
        if r.get("phone"):
            by_text[r["message"]].append(to_local(r["phone"], country_code))

    batches = [(text, nums[i:i + BATCH_SIZE]) for text, nums in by_text.items() for i in range(0, len(nums), BATCH_SIZE)]
    result = {"requests": 0, "sent": 0, "rejected": 0, "credit_used": 0, "credit_left": None, "error": None}
    for done, (text, numbers) in enumerate(batches, start=1):
        try:
            summary = send_quick(api_key, sender, numbers, text, http_post)
        except (SmsError, requests.RequestException) as err:
            result["error"] = str(err)
            break
        result["requests"] += 1
        result["sent"] += int(summary.get("total_sent", 0) or 0)
        result["rejected"] += int(summary.get("total_rejected", 0) or 0)
        result["credit_used"] += float(summary.get("credit_used", 0) or 0)
        result["credit_left"] = summary.get("credit_left", result["credit_left"])
        if on_progress:
            on_progress(done / len(batches))
    stopped_at = result["requests"]
    result["failed"] = len(batches[stopped_at][1]) if result["error"] else 0
    result["not_attempted"] = sum(len(n) for _, n in batches[stopped_at + 1:]) if result["error"] else 0
    return result
