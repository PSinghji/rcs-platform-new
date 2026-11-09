import os
import json
import pytz
from datetime import datetime

# Define IST globally for the providers
IST = pytz.timezone('Asia/Kolkata')

class ProviderAdapter:
    """
    Base class for all RCS provider adapters
    """

    def send_message(self, credentials, mobile, payload):
        raise NotImplementedError("send_message not implemented")

    def _log(self, filename, data):
        """
        Shared logger for all providers using IST timestamps.
        """
        log_dir = "/var/www/rcs-platform/logs"
        try:
            os.makedirs(log_dir, exist_ok=True)
            path = os.path.join(log_dir, filename)
            
            # Using IST instead of UTC for production logs
            timestamp = datetime.now(IST).strftime('%Y-%m-%d %H:%M:%S')
            
            with open(path, "a") as f:
                log_entry = {
                    "ts": timestamp,
                    "data": data
                }
                f.write(json.dumps(log_entry))
                f.write("\n") # One line per entry is better for large scale production
        except Exception as e:
            # Prevent the whole worker from crashing if logging fails
            print(f"Logging Error: {e}")