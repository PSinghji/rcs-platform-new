from .base import ProviderAdapter


class SmartPingAdapter(ProviderAdapter):
    name = "SmartPing"

    def check_capability(self, credentials, mobile):
        return 200, {"isRcsCapable": True}

    def send_message(self, credentials, payload):
        return 200, {"messageId": "smartping_dummy_id"}
