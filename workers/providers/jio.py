import json
import requests
import logging

# This logger will inherit settings from rcs_sender.py (File + Console)
logger = logging.getLogger("jio_adapter")

class JioAdapter:
    name = "jio"
    SEND_URL = "https://rcsapi.jiocx.com/api/v1/sendMessage"
    TIMEOUT = 30

    def send_bulk_messages(self, credentials, mobiles, payload, message_ids):
        """
        Sends RCS messages in bulk (up to 50 contacts) in a single API call.
        """
        # Format mobiles to include country code (+91)
        formatted_contacts = [f"+91{str(m).strip()}" if not str(m).startswith("+") else str(m) for m in mobiles]
        
        # Use the first message_id as the batch reference
        batch_id = message_ids[0] if message_ids else "batch_unknown"

        body = {
            "messageID": batch_id,
            "agentID": credentials["agent_id"],
            "contacts": formatted_contacts,
            "data": {
                "content": payload
            }
        }

        headers = {
            "Content-Type": "application/json",
            "x-apikey": credentials["api_key"]
        }

        try:
            resp = requests.post(
                self.SEND_URL,
                headers=headers,
                json=body,
                timeout=self.TIMEOUT
            )
            
            # --- CHANGED HERE: Use logger.info instead of print ---
            # This ensures it goes to /var/log/rcs_sender.log
            logger.info(f"📡 Jio Response [{resp.status_code}]: {resp.text}")

            try:
                data = resp.json()
            except Exception:
                data = {"raw": resp.text}
                
            return resp.status_code, data

        except Exception as e:
            logger.error(f"🔥 Jio API Critical Error: {str(e)}")
            return 500, {"error": str(e)}

    def send_message(self, credentials, mobile, payload, message_id):
        """
        Maintains backward compatibility for single message sending.
        """
        return self.send_bulk_messages(credentials, [mobile], payload, [message_id])