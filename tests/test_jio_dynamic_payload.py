import unittest
from unittest.mock import patch

from app.utils.template_variables import render_template_payload
from workers.providers.jio import JioAdapter


class FakeResponse:
    status_code = 200
    text = '{"messageID":"accepted-id"}'

    def json(self):
        return {"messageID": "accepted-id"}


class JioDynamicPayloadTests(unittest.TestCase):
    credentials = {"api_key": "test-key", "agent_id": "test-agent"}

    @patch("workers.providers.jio.requests.post")
    def test_simple_campaign_keeps_bulk_contacts(self, post):
        post.return_value = FakeResponse()
        status, response = JioAdapter().send_bulk_messages(
            self.credentials,
            ["9876543210", "9123456789"],
            {"plainText": "Common campaign message"},
            ["message-1", "message-2"],
        )

        self.assertEqual(status, 200)
        body = post.call_args.kwargs["json"]
        self.assertEqual(body["contacts"], ["+919876543210", "+919123456789"])
        self.assertEqual(body["data"]["content"]["plainText"], "Common campaign message")
        self.assertEqual(body["messageID"], "message-1")
        self.assertEqual(response["messageID"], "accepted-id")

    @patch("workers.providers.jio.requests.post")
    def test_dynamic_campaign_renders_recipient_before_jio_call(self, post):
        post.return_value = FakeResponse()
        template = {
            "plainText": "Hello {{name}}, your coupon is {{coupon_code}}.",
            "suggestions": [{
                "action": {
                    "plainText": "Use coupon",
                    "openUrl": {"url": "https://example.test/offers/{{coupon_code}}"},
                }
            }],
        }
        rendered = render_template_payload(
            template, {"name": "Asha", "coupon_code": "SAVE20"}
        )

        JioAdapter().send_message(
            self.credentials, "9876543210", rendered, "recipient-message-id"
        )

        body = post.call_args.kwargs["json"]
        self.assertEqual(body["contacts"], ["+919876543210"])
        self.assertEqual(body["messageID"], "recipient-message-id")
        self.assertEqual(body["data"]["content"]["plainText"], "Hello Asha, your coupon is SAVE20.")
        self.assertEqual(
            body["data"]["content"]["suggestions"][0]["action"]["openUrl"]["url"],
            "https://example.test/offers/SAVE20",
        )
        self.assertNotIn("{{", str(body))


if __name__ == "__main__":
    unittest.main()
