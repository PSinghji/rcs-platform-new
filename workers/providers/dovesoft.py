import json
import requests
import logging

logger = logging.getLogger("dovesoft_adapter")

class DoveSoftAdapter:
    name = "dovesoft"
    SEND_URL = "https://api.dovesoft.io/REST/direct/sendRCS"
    TIMEOUT = 20

    def send_bulk_messages(self, credentials, mobiles, payload, message_ids):
        # 1. DEFENSIVE CHECK
        api_key = credentials.get("api_key")
        if not api_key:
            logger.error("❌ DoveSoft Error: API Key is missing from credentials!")
            return 401, {"msg": "Auth Key Missing", "statusCode": 401}

        results = []
        success_count = 0
        
        # 2. TEMPLATE PARSING (Updated for your DB structure)
        # Based on your DB: payload is template['content']
        # We need the value inside 'plainText'
        if isinstance(payload, dict):
            template_code = payload.get("plainText", "test")
            # If your second service uses parameters, extract them; otherwise default to empty JSON string
            params = payload.get("custom_params", "{}")
        else:
            # Fallback if payload is somehow just a string
            template_code = payload 
            params = "{}"

        for i, mobile in enumerate(mobiles):
            formatted_mobile = f"+91{str(mobile).strip()}" if not str(mobile).startswith("+") else str(mobile)
            
            body = {
                "contentMessage": {
                    "templateMessage": {
                        "templateCode": template_code, # This will now be "Test20Jan"
                        "customParams": params
                    },
                    "mobileno": formatted_mobile,
                    "botId": credentials.get("agent_id"),
                    "messageId": message_ids[i]
                }
            }

            headers = {
                "key": str(api_key),
                "Content-Type": "application/json"
            }

            try:
                resp = requests.post(
                    self.SEND_URL,
                    headers=headers,
                    json=body,
                    timeout=self.TIMEOUT
                )
                
                logger.info(f"📡 DoveSoft [{formatted_mobile}] Response: {resp.text}")
                logger.info(f"📡 DoveSoft Body send: {body}")

                
                if resp.status_code == 200:
                    resp_data = resp.json()
                    # DoveSoft returns "status": true on success
                    if resp_data.get("status") is True or resp_data.get("message") == "sent":
                        success_count += 1
                    results.append(resp_data)
                else:
                    results.append({"error": resp.text, "statusCode": resp.status_code})

            except Exception as e:
                logger.error(f"🔥 DoveSoft Single Send Error: {str(e)}")
                results.append({"error": str(e)})

        if success_count > 0:
            return 200, results[0]
        else:
            # If nothing worked, return the first error found
            return 500, results[0] if results else {"error": "Failed"}

    def send_message(self, credentials, mobile, payload, message_id):
        return self.send_bulk_messages(credentials, [mobile], payload, [message_id])