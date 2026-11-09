from pathlib import Path

from docx import Document


SOURCE = Path(__file__).resolve().parents[1] / "RCS_API_Consumer_Guide.docx"


def replace_text(paragraph, old, new):
    if old not in paragraph.text:
        return False
    replacement = paragraph.text.replace(old, new)
    if paragraph.runs:
        paragraph.runs[0].text = replacement
        for run in paragraph.runs[1:]:
            run.text = ""
    else:
        paragraph.add_run(replacement)
    return True


document = Document(SOURCE)
changed = 0

for paragraph in document.paragraphs:
    changed += replace_text(paragraph, '  -H "Idempotency-Key: order-20261007-0001" \\\n', "")
    changed += replace_text(paragraph, '  -H "Idempotency-Key: order-20261007-0002" \\\n', "")
    changed += replace_text(
        paragraph,
        'campaign_headers = {\n    **headers,\n    "Idempotency-Key": "order-20261007-0003",\n}\n',
        "",
    )
    changed += replace_text(paragraph, "headers=campaign_headers,", "headers=headers,")
    changed += replace_text(paragraph, '    "Idempotency-Key": "order-20261007-0004",\n', "")
    changed += replace_text(
        paragraph,
        '  "campaign_id": "CAMPAIGN_ID"\n}',
        '  "campaign_id": "CAMPAIGN_ID",\n  "idempotency_key": "AUTO_GENERATED_UUID"\n}',
    )

if changed != 6:
    raise RuntimeError(f"Expected 6 guide example edits, made {changed}")

document.save(SOURCE)
print(f"Updated examples in {SOURCE}")
