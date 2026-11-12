import os
import unittest
from pathlib import Path


os.environ.setdefault("RCS_STATIC_PATH", "/tmp/rcs-platform-test-static")

from app.api_v1.campaigns import CampaignCreateRequest
from app.api_v1.portal import download_api_document, download_campaign_upload_sample
from app.api_v1.templates import TemplateCreateRequest
from app.main import app


class ApiDynamicContractTests(unittest.TestCase):
    def test_legacy_simple_campaign_numbers_remain_supported(self):
        request = CampaignCreateRequest(
            campaign_name="Simple Campaign",
            template_id="64f1234567890abcdef12345",
            numbers=["9876543210"],
        )
        self.assertEqual(request.numbers, ["9876543210"])
        self.assertEqual(request.recipients, [])

    def test_dynamic_campaign_accepts_inline_recipient_variables(self):
        request = CampaignCreateRequest(
            campaign_name="Dynamic Campaign",
            template_id="64f1234567890abcdef12345",
            recipients=[
                {
                    "mobile": "+919876543210",
                    "variables": {"name": "Asha", "coupon_code": "SAVE20"},
                }
            ],
        )
        self.assertEqual(request.recipients[0].mobile, "+919876543210")
        self.assertEqual(request.recipients[0].variables["name"], "Asha")

    def test_template_contract_documents_simple_and_dynamic_examples(self):
        examples = TemplateCreateRequest.model_json_schema()["examples"]
        self.assertEqual(examples[0]["content"]["plainText"], "Your service request has been completed.")
        self.assertIn("{{name}}", examples[1]["content"]["plainText"])

    def test_json_campaign_is_visible_in_openapi(self):
        schema = app.openapi()
        operation = schema["paths"]["/api/v1/campaigns"]["post"]
        self.assertEqual(operation["summary"], "Create Simple or Dynamic Campaign From JSON")
        request_schema = operation["requestBody"]["content"]["application/json"]["schema"]
        self.assertEqual(request_schema["$ref"], "#/components/schemas/CampaignCreateRequest")

    def test_downloads_resolve_to_packaged_artifacts(self):
        document = download_api_document(user={})
        workbook = download_campaign_upload_sample(user={})
        self.assertTrue(Path(document.path).is_file())
        self.assertTrue(Path(workbook.path).is_file())
        self.assertEqual(Path(document.path).name, "RCS_API_Consumer_Guide.docx")
        self.assertEqual(Path(workbook.path).name, "RCS_Campaign_Bulk_Upload_Template.xlsx")


if __name__ == "__main__":
    unittest.main()
