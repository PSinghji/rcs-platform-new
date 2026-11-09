from .base import ProviderAdapter


class AirtelAdapter(ProviderAdapter):
    name = "Airtel"

    def check_capability(self, credentials, mobile):
        # Implement Airtel capability API
        return 200, {"isRcsCapable": True}

    def send_message(self, credentials, payload):
        # Implement Airtel send API
        return 200, {"messageId": "airtel_dummy_id"}
