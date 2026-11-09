import unittest

from app.utils.template_variables import (
    extract_template_variables,
    missing_template_variables,
    normalize_variables,
    render_template_payload,
)


class TemplateVariableTests(unittest.TestCase):
    def setUp(self):
        self.payload = {
            "plainText": "Hello {{Name}}, your code is {{coupon_code}}.",
            "suggestions": [
                {"action": {"plainText": "Open", "openUrl": {"url": "https://example.test/{{coupon_code}}"}}}
            ],
        }

    def test_extracts_nested_variables_in_normalized_form(self):
        self.assertEqual(extract_template_variables(self.payload), ["coupon_code", "name"])

    def test_renders_nested_payload_without_mutating_template(self):
        rendered = render_template_payload(self.payload, {"Name": "Asha", "Coupon Code": "SAVE20"})
        self.assertEqual(rendered["plainText"], "Hello Asha, your code is SAVE20.")
        self.assertEqual(
            rendered["suggestions"][0]["action"]["openUrl"]["url"],
            "https://example.test/SAVE20",
        )
        self.assertIn("{{Name}}", self.payload["plainText"])

    def test_missing_values_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "coupon_code"):
            render_template_payload(self.payload, {"name": "Asha"})

    def test_normalizes_uploaded_column_names(self):
        values = normalize_variables({"Customer Name": " Asha ", "Coupon-Code": " X1 "})
        self.assertEqual(values, {"customer_name": "Asha", "coupon_code": "X1"})

    def test_reports_missing_required_values(self):
        self.assertEqual(
            missing_template_variables(["name", "coupon_code"], {"name": "Asha"}),
            ["coupon_code"],
        )


if __name__ == "__main__":
    unittest.main()
