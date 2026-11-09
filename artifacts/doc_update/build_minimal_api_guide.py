from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Inches, Pt, RGBColor


OUTPUT = Path(__file__).resolve().parents[1] / "RCS_API_Consumer_Guide.docx"
BLUE = "245781"
PALE = "F2F6FA"
BORDER = "D9D9D9"


def font(run, name="Aptos", size=10.5, bold=False, color="253142"):
    run.font.name = name
    run._element.get_or_add_rPr().rFonts.set(qn("w:ascii"), name)
    run._element.get_or_add_rPr().rFonts.set(qn("w:hAnsi"), name)
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)


def shade(cell, fill):
    tc_pr = cell._tc.get_or_add_tcPr()
    shd = tc_pr.find(qn("w:shd")) or OxmlElement("w:shd")
    shd.set(qn("w:fill"), fill)
    tc_pr.append(shd)


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
    p.paragraph_format.space_before = Pt(10)
    p.paragraph_format.space_after = Pt(5)
    for run in p.runs:
        font(run, size=18 if level == 1 else 13, bold=True, color="000000")
    return p


def body(document, text, bold_prefix=None):
    p = document.add_paragraph()
    p.paragraph_format.space_after = Pt(5)
    p.paragraph_format.line_spacing = 1.12
    if bold_prefix and text.startswith(bold_prefix):
        r = p.add_run(bold_prefix)
        font(r, bold=True, color="000000")
        r = p.add_run(text[len(bold_prefix):])
        font(r)
    else:
        r = p.add_run(text)
        font(r)
    return p


def code(document, text):
    p = document.add_paragraph()
    p.paragraph_format.left_indent = Inches(0.14)
    p.paragraph_format.right_indent = Inches(0.14)
    p.paragraph_format.space_before = Pt(2)
    p.paragraph_format.space_after = Pt(8)
    p.paragraph_format.line_spacing = 1.0
    shd = OxmlElement("w:shd")
    shd.set(qn("w:fill"), "EEF3F8")
    p._p.get_or_add_pPr().append(shd)
    r = p.add_run(text)
    font(r, name="Courier New", size=8.4)


def endpoint(document, method, path, purpose):
    p = document.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(3)
    r = p.add_run(f"{method}  ")
    font(r, size=11.5, bold=True, color=BLUE)
    r = p.add_run(path)
    font(r, name="Courier New", size=10.5, bold=True, color="172333")
    body(document, purpose)


document = Document()
section = document.sections[0]
section.top_margin = Inches(0.65)
section.bottom_margin = Inches(0.65)
section.left_margin = Inches(0.7)
section.right_margin = Inches(0.7)

styles = document.styles
styles["Normal"].font.name = "Aptos"
styles["Normal"].font.size = Pt(10.5)
for style_name in ("Title", "Heading 1", "Heading 2"):
    styles[style_name].font.color.rgb = RGBColor(0, 0, 0)

title = document.add_paragraph()
title.paragraph_format.space_after = Pt(12)
r = title.add_run("RCS Platform Minimal API Guide")
font(r, size=27, bold=True, color="000000")
body(document, "Production base URL  https://rcs.ostpl.com", bold_prefix="Production base URL")
body(document, "This guide contains only the seven endpoints required to authenticate, create and approve a template, select an approved template, send a campaign, monitor it, and download its report.")

heading(document, "Required flow")
steps = [
    "Generate an access token using the portal username and password.",
    "Create a template and save the returned template_id.",
    "Check the template status until it is approved.",
    "List approved templates and select the required template_id.",
    "Upload a CSV, TXT, or XLSX number file to create the campaign.",
    "Check the campaign status until processing completes.",
    "Download the CSV report.",
]
for i, item in enumerate(steps, 1):
    body(document, f"{i}. {item}")

heading(document, "Endpoint summary")
rows = [
    ("POST", "/api/v1/auth/token", "Generate access token"),
    ("POST", "/api/v1/templates", "Create template"),
    ("GET", "/api/v1/templates/{template_id}/status", "Check template approval"),
    ("GET", "/api/v1/templates/approved", "List approved templates"),
    ("POST", "/api/v1/campaigns/upload", "Upload and send campaign"),
    ("GET", "/api/v1/campaigns/{campaign_id}/status", "Monitor campaign"),
    ("GET", "/api/v1/campaigns/{campaign_id}/report", "Download CSV report"),
]
table = document.add_table(rows=1, cols=3)
table.autofit = False
widths = [Inches(0.8), Inches(3.55), Inches(2.55)]
headers = ["Method", "Endpoint", "Purpose"]
for i, cell in enumerate(table.rows[0].cells):
    cell.width = widths[i]
    shade(cell, BLUE)
    cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
    cell.text = headers[i]
    for run in cell.paragraphs[0].runs:
        font(run, size=9.5, bold=True, color="FFFFFF")
for row_no, row in enumerate(rows):
    cells = table.add_row().cells
    for i, value in enumerate(row):
        cells[i].width = widths[i]
        cells[i].vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
        cells[i].text = value
        if row_no % 2:
            shade(cells[i], PALE)
        for run in cells[i].paragraphs[0].runs:
            font(run, size=9.2)
borders(table)

document.add_page_break()
heading(document, "1 Authentication")
endpoint(document, "POST", "/api/v1/auth/token", "Generate an access token using the same username and password used in the portal.")
code(document, '''curl -X POST "https://rcs.ostpl.com/api/v1/auth/token" \\
  -H "Content-Type: application/json" \\
  -d '{"username":"YOUR_USERNAME","password":"YOUR_PASSWORD"}' ''')
body(document, "Use the returned access_token in every protected request:")
code(document, "Authorization: Bearer ACCESS_TOKEN")

heading(document, "2 Create template")
endpoint(document, "POST", "/api/v1/templates", "Create a template. A non-admin template remains pending until an administrator approves it.")
code(document, '''curl -X POST "https://rcs.ostpl.com/api/v1/templates" \\
  -H "Authorization: Bearer ACCESS_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{
    "name": "October Offer",
    "template_type": "plain",
    "content": {"text": "Your offer message"}
  }' ''')
body(document, "Save template_id from the response.")

heading(document, "3 Check template approval")
endpoint(document, "GET", "/api/v1/templates/{template_id}/status", "Continue only after the returned status becomes approved.")
code(document, '''curl "https://rcs.ostpl.com/api/v1/templates/TEMPLATE_ID/status" \\
  -H "Authorization: Bearer ACCESS_TOKEN"''')

heading(document, "4 List approved templates")
endpoint(document, "GET", "/api/v1/templates/approved", "Return approved templates that are eligible for campaign creation. Copy the required item id and use it as template_id.")
code(document, '''curl "https://rcs.ostpl.com/api/v1/templates/approved?limit=100" \\
  -H "Authorization: Bearer ACCESS_TOKEN"''')

document.add_page_break()
heading(document, "5 Upload and send campaign")
endpoint(document, "POST", "/api/v1/campaigns/upload", "Create a campaign from a CSV, TXT, or XLSX file containing mobile numbers.")
code(document, '''curl -X POST "https://rcs.ostpl.com/api/v1/campaigns/upload" \\
  -H "Authorization: Bearer ACCESS_TOKEN" \\
  -F "campaign_name=October Campaign" \\
  -F "template_id=TEMPLATE_ID" \\
  -F "numbers_file=@RCS_Campaign_Bulk_Upload_Template.xlsx"''')
body(document, "The Idempotency-Key header is not required. The server automatically generates a UUID and returns it as idempotency_key. A caller may optionally provide a stable key when retrying the same request.")
body(document, "Upload limits: 20 MB and 500,000 unique valid Indian mobile numbers. Accepted files are UTF-8 CSV, plain text, or XLSX. An XLSX file must contain a Mobile column in the first worksheet. Download the sample workbook from the API Integration page in the portal.")

heading(document, "6 Monitor campaign")
endpoint(document, "GET", "/api/v1/campaigns/{campaign_id}/status", "Use the campaign_id returned by the upload endpoint.")
code(document, '''curl "https://rcs.ostpl.com/api/v1/campaigns/CAMPAIGN_ID/status" \\
  -H "Authorization: Bearer ACCESS_TOKEN"''')

heading(document, "7 Download report")
endpoint(document, "GET", "/api/v1/campaigns/{campaign_id}/report", "Download the authorized campaign report as CSV.")
code(document, '''curl "https://rcs.ostpl.com/api/v1/campaigns/CAMPAIGN_ID/report" \\
  -H "Authorization: Bearer ACCESS_TOKEN" \\
  --output campaign-report.csv''')
body(document, "Optional filter: add ?status=delivered, ?status=failed, ?status=read, or another supported message status.")

heading(document, "Security and error handling")
for item in [
    "Use HTTPS only and keep passwords and access tokens out of URLs and logs.",
    "HTTP 401 means the access token is missing, invalid, or expired. Generate a new token.",
    "HTTP 402 means the wallet balance is insufficient.",
    "HTTP 404 means the template or campaign was not found or is not accessible to the user.",
    "HTTP 413 means the upload exceeds the file or number limit.",
    "HTTP 422 means a required request field is missing or invalid.",
]:
    body(document, f"• {item}")

for section in document.sections:
    footer = section.footer.paragraphs[0]
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    r = footer.add_run("RCS Platform Minimal API Guide")
    font(r, size=8.5, color="68788C")

document.save(OUTPUT)
print(f"Created {OUTPUT}")
