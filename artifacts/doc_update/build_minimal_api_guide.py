from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


OUTPUT = Path(__file__).resolve().parents[1] / "RCS_API_Consumer_Guide.docx"
BLUE = "0B63CE"
DARK = "172333"
MUTED = "526273"
PALE_BLUE = "EEF5FF"
PALE_GRAY = "F4F6F8"
BORDER = "D6DEE8"
GREEN = "16865A"


def font(run, name="Aptos", size=10.2, bold=False, color=DARK):
    run.font.name = name
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), name)
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)


def shade(target, fill):
    properties = target._tc.get_or_add_tcPr() if hasattr(target, "_tc") else target._p.get_or_add_pPr()
    shd = properties.find(qn("w:shd")) or OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    properties.append(shd)


def borders(table):
    tbl_pr = table._tbl.tblPr
    item = tbl_pr.find(qn("w:tblBorders")) or OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        el = OxmlElement(f"w:{edge}")
        el.set(qn("w:val"), "single")
        el.set(qn("w:sz"), "4")
        el.set(qn("w:color"), BORDER)
        item.append(el)
    tbl_pr.append(item)


def heading(document, text, level=1):
    p = document.add_heading(text, level=level)
    p.paragraph_format.space_before = Pt(11 if level == 1 else 8)
    p.paragraph_format.space_after = Pt(5)
    p.paragraph_format.keep_with_next = True
    for run in p.runs:
        font(run, size=18 if level == 1 else 12.5, bold=True, color=DARK)
    return p


def body(document, text, *, bold_prefix=None, color=MUTED, after=5):
    p = document.add_paragraph()
    p.paragraph_format.space_after = Pt(after)
    p.paragraph_format.line_spacing = 1.12
    if bold_prefix and text.startswith(bold_prefix):
        font(p.add_run(bold_prefix), bold=True, color=DARK)
        font(p.add_run(text[len(bold_prefix):]), color=color)
    else:
        font(p.add_run(text), color=color)
    return p


def bullet(document, text):
    p = document.add_paragraph(style="List Bullet")
    p.paragraph_format.space_after = Pt(3)
    p.paragraph_format.left_indent = Inches(0.24)
    p.paragraph_format.first_line_indent = Inches(-0.14)
    font(p.add_run(text), color=MUTED)
    return p


def code(document, text):
    p = document.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.12)
    p.paragraph_format.right_indent = Inches(0.12)
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(7)
    p.paragraph_format.line_spacing = 1.0
    shade(p, PALE_GRAY)
    font(p.add_run(text.strip()), name="Courier New", size=7.6, color="1F2933")
    return p


def callout(document, title, text, fill=PALE_BLUE):
    table = document.add_table(rows=1, cols=1)
    table.autofit = False
    cell = table.cell(0, 0)
    shade(cell, fill)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    p = cell.paragraphs[0]
    p.paragraph_format.space_after = Pt(2)
    font(p.add_run(title), size=10.4, bold=True, color=BLUE)
    p = cell.add_paragraph()
    p.paragraph_format.space_after = Pt(0)
    p.paragraph_format.line_spacing = 1.08
    font(p.add_run(text), size=9.6, color=DARK)
    document.add_paragraph().paragraph_format.space_after = Pt(0)


def endpoint(document, method, path, purpose):
    p = document.add_paragraph()
    p.paragraph_format.space_before = Pt(7)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    font(p.add_run(f"{method}  "), size=10.8, bold=True, color=GREEN if method == "GET" else BLUE)
    font(p.add_run(path), name="Courier New", size=9.8, bold=True, color=DARK)
    body(document, purpose, after=3)


def add_page_number(paragraph):
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    font(paragraph.add_run("RCS Platform API Guide  •  "), size=8.2, color="788696")
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    instruction = OxmlElement("w:instrText")
    instruction.set(qn("xml:space"), "preserve")
    instruction.text = " PAGE "
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run._r.append(begin)
    run._r.append(instruction)
    run._r.append(end)
    font(run, size=8.2, color="788696")


document = Document()
section = document.sections[0]
section.top_margin = Inches(0.58)
section.bottom_margin = Inches(0.55)
section.left_margin = Inches(0.68)
section.right_margin = Inches(0.68)

styles = document.styles
styles["Normal"].font.name = "Aptos"
styles["Normal"].font.size = Pt(10.2)
for style_name in ("Title", "Heading 1", "Heading 2"):
    styles[style_name].font.color.rgb = RGBColor.from_string(DARK)

title = document.add_paragraph()
title.paragraph_format.space_after = Pt(3)
font(title.add_run("RCS Platform"), size=15, bold=True, color=BLUE)
title = document.add_paragraph()
title.paragraph_format.space_after = Pt(8)
font(title.add_run("API Integration Guide"), size=28, bold=True, color=DARK)
body(document, "Production base URL  https://rcs.ostpl.com", bold_prefix="Production base URL", color=DARK)
body(
    document,
    "Create simple or personalized RCS templates, submit campaigns using JSON parameters or an optional audience file, monitor processing, and download delivery reports.",
    color=MUTED,
    after=10,
)
callout(
    document,
    "Dynamic campaigns do not require CSV",
    "Define placeholders in the template, then pass each recipient's values in recipients[].variables when calling POST /api/v1/campaigns. The existing numbers field remains supported for simple campaigns.",
)

heading(document, "Recommended integration flow")
steps = [
    "Authenticate and store the returned access token securely.",
    "Create a simple template or add {{placeholder}} values to create a dynamic template.",
    "Check approval status and obtain an approved template_id.",
    "Submit a simple or dynamic campaign as JSON, or use file upload for large lists.",
    "Monitor campaign status and download the CSV delivery report.",
]
for index, item in enumerate(steps, 1):
    body(document, f"{index}. {item}", color=DARK, after=4)

heading(document, "Compatibility promise", level=2)
bullet(document, "Existing endpoint URLs are unchanged.")
bullet(document, "Existing simple JSON integrations can continue sending numbers.")
bullet(document, "CSV, TXT, and XLSX upload remains available; XLSX uses a Mobile column.")

document.add_page_break()
heading(document, "Endpoint reference")
rows = [
    ("POST", "/api/v1/auth/token", "Generate access token"),
    ("POST", "/api/v1/templates", "Create simple or dynamic template"),
    ("GET", "/api/v1/templates/{template_id}/status", "Check template approval"),
    ("GET", "/api/v1/templates/approved", "List approved templates"),
    ("POST", "/api/v1/campaigns", "Create JSON campaign without a file"),
    ("POST", "/api/v1/campaigns/upload", "Create campaign from CSV/TXT/XLSX"),
    ("GET", "/api/v1/campaigns/{campaign_id}/status", "Monitor campaign"),
    ("GET", "/api/v1/campaigns/{campaign_id}/report", "Download CSV report"),
]
table = document.add_table(rows=1, cols=3)
table.autofit = False
widths = [Inches(0.72), Inches(3.45), Inches(2.55)]
for index, (cell, label) in enumerate(zip(table.rows[0].cells, ("Method", "Endpoint", "Purpose"))):
    cell.width = widths[index]
    shade(cell, BLUE)
    cell.text = label
    for run in cell.paragraphs[0].runs:
        font(run, size=9.1, bold=True, color="FFFFFF")
for row_number, row in enumerate(rows):
    cells = table.add_row().cells
    for index, value in enumerate(row):
        cells[index].width = widths[index]
        cells[index].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        cells[index].text = value
        if row_number % 2:
            shade(cells[index], PALE_GRAY)
        for run in cells[index].paragraphs[0].runs:
            font(run, name="Courier New" if index == 1 else "Aptos", size=8.5)
borders(table)

body(document, "Interactive Swagger reference: https://rcs.ostpl.com/docs", bold_prefix="Interactive Swagger reference:", color=DARK, after=3)
body(document, "Use the Authorize button once, then run protected operations directly from the reference page.")

document.add_page_break()
heading(document, "Template modes")
heading(document, "Simple", level=2)
body(document, "A simple template contains fixed content. Send its campaign using the existing numbers array or a one-column upload file.")
heading(document, "Dynamic", level=2)
body(document, "A dynamic template contains placeholders in the form {{name}}. Placeholders are detected recursively in every string field, including plain text, rich-card titles, descriptions, URLs, and action values.")
bullet(document, "Names must start with a letter and may contain letters, numbers, and underscores.")
bullet(document, "Names are normalized to lowercase by the platform.")
bullet(document, "Every recipient must supply a non-empty value for every required placeholder.")
bullet(document, "Dynamic sending is currently supported with the Jio RCS provider.")

document.add_page_break()
heading(document, "1. Authentication")
endpoint(document, "POST", "/api/v1/auth/token", "Use the same username and password used in the portal.")
code(document, '''curl -X POST "https://rcs.ostpl.com/api/v1/auth/token" \\
  -H "Content-Type: application/json" \\
  -d '{"username":"YOUR_USERNAME","password":"YOUR_PASSWORD"}' ''')
body(document, "Send the returned access_token in protected calls:", color=DARK)
code(document, "Authorization: Bearer ACCESS_TOKEN")

heading(document, "2. Create a simple template")
endpoint(document, "POST", "/api/v1/templates", "Create fixed RCS content. A non-admin template remains pending until approved by an administrator.")
code(document, '''curl -X POST "https://rcs.ostpl.com/api/v1/templates" \\
  -H "Authorization: Bearer ACCESS_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "Simple Service Update",
    "template_type": "plain",
    "content": {"plainText": "Your service request has been completed."}
  }' ''')

heading(document, "3. Create a dynamic template")
endpoint(document, "POST", "/api/v1/templates", "Add placeholders wherever recipient-specific values are required. The response returns template_id; the approved-template response includes message_mode and variables.")
code(document, '''curl -X POST "https://rcs.ostpl.com/api/v1/templates" \\
  -H "Authorization: Bearer ACCESS_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "Dynamic Coupon Offer",
    "template_type": "plain",
    "content": {
      "plainText": "Hello {{name}}, use {{coupon_code}} before {{expiry_date}}."
    }
  }' ''')

heading(document, "4. Approval and selection")
code(document, '''curl "https://rcs.ostpl.com/api/v1/templates/TEMPLATE_ID/status" \\
  -H "Authorization: Bearer ACCESS_TOKEN"

curl "https://rcs.ostpl.com/api/v1/templates/approved?limit=100" \\
  -H "Authorization: Bearer ACCESS_TOKEN"''')

document.add_page_break()
heading(document, "5. Create campaigns from JSON")
callout(
    document,
    "Use one audience field",
    "Use numbers for a simple template. Use recipients for a dynamic template. If both are supplied, recipients takes precedence.",
)

heading(document, "Simple JSON campaign", level=2)
body(document, "The legacy numbers request is unchanged and requires no CSV file.")
code(document, '''curl -X POST "https://rcs.ostpl.com/api/v1/campaigns" \\
  -H "Authorization: Bearer ACCESS_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "campaign_name": "Simple November Campaign",
    "template_id": "APPROVED_TEMPLATE_ID",
    "numbers": ["9876543210", "+919123456789"]
  }' ''')

heading(document, "Dynamic JSON campaign — no CSV", level=2)
body(document, "Each recipients item contains mobile and a variables object. Variable keys must match the approved template placeholders; values may be strings, numbers, or booleans and are rendered as text.")
code(document, '''curl -X POST "https://rcs.ostpl.com/api/v1/campaigns" \\
  -H "Authorization: Bearer ACCESS_TOKEN" \\
  -H "Content-Type: application/json" \\
  -H "Idempotency-Key: campaign-request-20261112-001" \\
  -d '{
    "campaign_name": "Personalized November Campaign",
    "template_id": "APPROVED_DYNAMIC_TEMPLATE_ID",
    "recipients": [
      {
        "mobile": "9876543210",
        "variables": {
          "name": "Asha",
          "coupon_code": "SAVE20",
          "expiry_date": "30 November 2026"
        }
      },
      {
        "mobile": "+919123456789",
        "variables": {
          "name": "Ravi",
          "coupon_code": "SAVE10",
          "expiry_date": "30 November 2026"
        }
      }
    ]
  }' ''')
body(document, "The Idempotency-Key header is optional. Supply a stable value of 8–128 characters when safely retrying the same request; otherwise the server generates a UUID and returns it.")

document.add_page_break()
heading(document, "6. Optional file upload")
endpoint(document, "POST", "/api/v1/campaigns/upload", "Use an upload for large audiences. Dynamic XLSX/CSV files may add columns whose normalized headings match template placeholders.")
code(document, '''curl -X POST "https://rcs.ostpl.com/api/v1/campaigns/upload" \\
  -H "Authorization: Bearer ACCESS_TOKEN" \\
  -F "campaign_name=November Campaign" \\
  -F "template_id=APPROVED_TEMPLATE_ID" \\
  -F "numbers_file=@RCS_Campaign_Bulk_Upload_Template.xlsx"''')
bullet(document, "Maximum file size: 20 MB.")
bullet(document, "Maximum audience: 500,000 unique valid Indian mobile numbers.")
bullet(document, "Accepted formats: UTF-8 CSV, TXT, and XLSX.")
bullet(document, "XLSX uses the first worksheet and requires a Mobile column.")

heading(document, "7. Monitor and report")
endpoint(document, "GET", "/api/v1/campaigns/{campaign_id}/status", "Monitor queue, sent, delivered, read, and failed totals.")
code(document, '''curl "https://rcs.ostpl.com/api/v1/campaigns/CAMPAIGN_ID/status" \\
  -H "Authorization: Bearer ACCESS_TOKEN"''')
endpoint(document, "GET", "/api/v1/campaigns/{campaign_id}/report", "Download the authorized campaign report as CSV. Add ?status=delivered, ?status=failed, or another supported status to filter it.")
code(document, '''curl "https://rcs.ostpl.com/api/v1/campaigns/CAMPAIGN_ID/report" \\
  -H "Authorization: Bearer ACCESS_TOKEN" \\
  --output campaign-report.csv''')

heading(document, "Validation and errors")
error_rows = [
    ("400", "Invalid template, provider, recipient, or missing dynamic value"),
    ("401", "Access token is missing, invalid, or expired"),
    ("402", "Wallet balance is insufficient"),
    ("404", "Authorized template or campaign was not found"),
    ("409", "Campaign name or idempotency-key conflict"),
    ("413", "JSON audience, uploaded file, or upload audience exceeds a limit"),
    ("422", "Required request field is missing or has the wrong type"),
]
table = document.add_table(rows=1, cols=2)
table.autofit = False
for index, (cell, label) in enumerate(zip(table.rows[0].cells, ("HTTP", "Meaning"))):
    cell.width = Inches(0.7 if index == 0 else 5.95)
    shade(cell, BLUE)
    cell.text = label
    for run in cell.paragraphs[0].runs:
        font(run, size=9, bold=True, color="FFFFFF")
for row_number, row in enumerate(error_rows):
    cells = table.add_row().cells
    for index, value in enumerate(row):
        cells[index].text = value
        if row_number % 2:
            shade(cells[index], PALE_GRAY)
        for run in cells[index].paragraphs[0].runs:
            font(run, size=8.6, bold=index == 0)
borders(table)

heading(document, "Security notes", level=2)
bullet(document, "Use HTTPS only. Never place passwords or access tokens in URLs or logs.")
bullet(document, "Store bearer tokens and any provider credentials in a secrets manager.")
bullet(document, "Users can monitor and download only campaigns they are authorized to access.")

for doc_section in document.sections:
    add_page_number(doc_section.footer.paragraphs[0])

document.save(OUTPUT)
print(f"Created {OUTPUT}")
