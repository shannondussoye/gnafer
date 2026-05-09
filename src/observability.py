import os
import requests
import logging
from logtail import LogtailHandler
from dotenv import load_dotenv

load_dotenv()

class GeocoderObservability:
    def __init__(self):
        self.logtail_token = os.getenv("LOGTAIL_TOKEN")
        self.hc_url = os.getenv("HEALTHCHECKS_URL")
        
        # Setup Recorder (Logtail)
        self.logger = logging.getLogger("gnafer")
        if self.logtail_token and "your_token" not in self.logtail_token:
            handler = LogtailHandler(source_token=self.logtail_token)
            self.logger.addHandler(handler)
            self.logger.info("Observability: Logtail Recorder initialized.")
        else:
            self.logger.info("Observability: Logtail disabled (no token).")

    def log_progress(self, message: str, metadata: dict = None):
        """Log structured data to the cloud."""
        self.logger.info(message, extra=metadata if metadata else {})

    def send_pulse(self):
        """Send a heartbeat to Healthchecks.io."""
        if self.hc_url and "your-uuid" not in self.hc_url:
            try:
                requests.get(self.hc_url, timeout=5)
            except Exception as e:
                self.logger.warning(f"Pulse failed: {e}")

    def log_completion(self, stats: dict):
        """Log final batch statistics."""
        self.log_progress("Geocoding Batch Complete", stats)
        # Final success ping to Healthchecks
        if self.hc_url and "your-uuid" not in self.hc_url:
            requests.get(f"{self.hc_url}/complete", timeout=5)
