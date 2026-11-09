from pathlib import Path

from docx import Document


SOURCE = Path(__file__).resolve().parents[1] / "RCS_API_Consumer_Guide.docx"

REPLACEMENTS = {
    "3. Create a campaign with a unique Idempotency Key.":
        "3. Create a campaign. The server generates an idempotency key automatically.",
    "Idempotency Key": "Optional Idempotency Key",
    (
        "Every campaign creation request requires an Idempotency Key header containing 8 to 128 characters. "
        "Generate one unique value per intended campaign. Retrying an identical completed request with the same "
        "key returns the original response. Reusing the key with different input returns HTTP 409."
    ): (
        "The Idempotency-Key header is optional. When it is omitted, the server generates a UUID automatically "
        "and returns it as idempotency_key in the campaign response. Integrations may still supply an 8 to 128 "
        "character key when they need to retry the same request safely. Retrying an identical completed request "
        "with the same supplied key returns the original response. Reusing that key with different input returns HTTP 409."
    ),
    "For temporary HTTP 500 or network failures, retry with exponential backoff and the same Idempotency Key.":
        "For temporary HTTP 500 or network failures, retry with exponential backoff. If the client supplied an Idempotency-Key, reuse that same key.",
    "Never generate a new Idempotency Key merely because the client did not receive the original campaign response.":
        "When a client supplies an Idempotency-Key, do not generate a new one merely because the original campaign response was not received.",
}


def iter_paragraphs(document):
    yield from document.paragraphs
    for table in document.tables:
        for row in table.rows:
            for cell in row.cells:
                yield from cell.paragraphs


document = Document(SOURCE)
found = {key: 0 for key in REPLACEMENTS}

for paragraph in iter_paragraphs(document):
    text = paragraph.text
    if text in REPLACEMENTS:
        replacement = REPLACEMENTS[text]
        found[text] += 1
        if paragraph.runs:
            paragraph.runs[0].text = replacement
            for run in paragraph.runs[1:]:
                run.text = ""
        else:
            paragraph.add_run(replacement)

missing = [text for text, count in found.items() if count == 0]
if missing:
    raise RuntimeError(f"Expected guide text not found: {missing}")

document.save(SOURCE)
print(f"Updated {SOURCE}")
