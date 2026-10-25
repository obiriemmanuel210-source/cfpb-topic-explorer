"""PDF giving statements (receipts) for members.

Uses the bundled DejaVu Sans font so names with letters such as ɔ, ɛ, ŋ
and currency signs such as ₵ or ₦ print correctly.
"""

import io
import zipfile
from pathlib import Path

from fpdf import FPDF

FONT_DIR = Path(__file__).parent / "fonts"


def _pdf():
    pdf = FPDF(format="A4")
    pdf.add_font("DejaVu", "", str(FONT_DIR / "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", str(FONT_DIR / "DejaVuSans-Bold.ttf"))
    pdf.set_auto_page_break(auto=True, margin=18)
    return pdf


def giving_statement(member, gifts, start, end, church_name, currency, church_details="", signatory=""):
    """Build one statement PDF and return its bytes.

    `member` is a dict from db.get_member, `gifts` the DataFrame from
    db.list_donations for that member and period.
    """
    pdf = _pdf()
    pdf.add_page()
    pdf.set_font("DejaVu", "B", 16)
    pdf.cell(0, 9, church_name, new_x="LMARGIN", new_y="NEXT")
    if church_details:
        pdf.set_font("DejaVu", "", 9)
        pdf.multi_cell(0, 5, church_details, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    pdf.set_font("DejaVu", "B", 13)
    pdf.cell(0, 8, "Statement of Giving", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("DejaVu", "", 10)
    pdf.cell(0, 6, f"Period: {start:%d %b %Y} to {end:%d %b %Y}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)
    pdf.cell(0, 6, f"{member['first_name']} {member['last_name']}", new_x="LMARGIN", new_y="NEXT")
    for line in (member.get("address"), member.get("phone"), member.get("email")):
        if line:
            pdf.cell(0, 5, str(line), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(4)

    widths = (32, 58, 50, 40)
    pdf.set_font("DejaVu", "B", 10)
    pdf.set_fill_color(235, 235, 235)
    for w, h in zip(widths, ("Date", "Fund", "Method", "Amount")):
        pdf.cell(w, 7, h, border=1, fill=True, align="R" if h == "Amount" else "L")
    pdf.ln()
    pdf.set_font("DejaVu", "", 10)
    for g in gifts.sort_values("donation_date").itertuples():
        pdf.cell(widths[0], 7, str(g.donation_date), border=1)
        pdf.cell(widths[1], 7, str(g.fund), border=1)
        pdf.cell(widths[2], 7, str(g.method or ""), border=1)
        pdf.cell(widths[3], 7, f"{currency}{g.amount:,.2f}", border=1, align="R")
        pdf.ln()
    pdf.set_font("DejaVu", "B", 10)
    pdf.cell(sum(widths[:3]), 7, "Total", border=1)
    pdf.cell(widths[3], 7, f"{currency}{gifts['amount'].sum():,.2f}", border=1, align="R")
    pdf.ln(10)

    if len(gifts):
        pdf.set_font("DejaVu", "", 10)
        by_fund = gifts.groupby("fund")["amount"].sum()
        pdf.cell(0, 6, "Summary by fund: " + ", ".join(f"{f} {currency}{a:,.2f}" for f, a in by_fund.items()),
                 new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)

    pdf.set_font("DejaVu", "", 10)
    pdf.multi_cell(0, 5, "Thank you for your faithful giving. Please keep this statement for your records "
                         "and contact the church office if anything on it looks wrong.",
                   new_x="LMARGIN", new_y="NEXT")
    if signatory:
        pdf.ln(12)
        pdf.cell(70, 0, "", border="T", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(2)
        pdf.cell(0, 5, signatory, new_x="LMARGIN", new_y="NEXT")
    return bytes(pdf.output())


def statements_zip(items):
    """Zip several statements. `items` is a list of (filename, pdf_bytes)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in items:
            zf.writestr(name, data)
    return buf.getvalue()
