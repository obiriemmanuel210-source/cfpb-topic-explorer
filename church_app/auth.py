"""Passwords and roles.

Passwords are stored as salted PBKDF2 hashes (Python standard library), so
the database never holds a readable password.
"""

import hashlib
import hmac
import secrets

ITERATIONS = 310_000
MIN_PASSWORD_LENGTH = 8

# What each role can open. Admins can do everything.
ROLES = {
    "admin": "Admin: everything, including user accounts, backups and the audit log",
    "finance": "Finance: giving, pledges, statements, plus read-only member list",
    "pastoral": "Pastoral / secretary: members, groups, attendance, events, children, messages (no giving)",
    "children": "Children's ministry volunteer: child check-in and check-out only",
}

PAGE_ACCESS = {
    "Dashboard": {"admin", "finance", "pastoral"},
    "Members": {"admin", "finance", "pastoral"},
    "Groups": {"admin", "pastoral"},
    "Attendance": {"admin", "pastoral"},
    "Giving": {"admin", "finance"},
    "Children": {"admin", "pastoral", "children"},
    "Events": {"admin", "pastoral"},
    "Messages": {"admin", "pastoral", "finance"},
    "Admin": {"admin"},
}


def can(role, page):
    return role in PAGE_ACCESS.get(page, set())


def can_edit_members(role):
    return role in {"admin", "pastoral"}


def sees_giving(role):
    return role in {"admin", "finance"}


def hash_password(password):
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, ITERATIONS)
    return f"pbkdf2_sha256${ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password, stored):
    try:
        algo, iterations, salt_hex, digest_hex = stored.split("$")
    except (AttributeError, ValueError):
        return False
    if algo != "pbkdf2_sha256":
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
    return hmac.compare_digest(digest.hex(), digest_hex)


def password_problem(password):
    """Return a reason the password is too weak, or None if it is acceptable."""
    if len(password or "") < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if password.lower() in {"password", "password1", "12345678", "123456789", "church123", "qwertyui"}:
        return "That password is too easy to guess."
    return None
