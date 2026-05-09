import os
import logging
import sys
from logtail import LogtailHandler
from dotenv import load_dotenv

load_dotenv()

class GeocoderObservability:
    def __init__(self):
        self.logtail_token = os.getenv("LOGTAIL_TOKEN")
        
        # Setup Recorder (Logtail)
        self.logger = logging.getLogger("gnafer")
        self.logger.setLevel(logging.INFO)
        
        # Local console logging
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        self.logger.addHandler(console_handler)

        if self.logtail_token and "your_token" not in self.logtail_token:
            handler = LogtailHandler(source_token=self.logtail_token)
            self.logger.addHandler(handler)
            self.logger.info("Observability: Logtail Recorder initialized.")
        else:
            self.logger.info("Observability: Logtail disabled (no token).")

    def log_progress(self, message: str, metadata: dict = None):
        """Log structured data to the cloud."""
        self.logger.info(message, extra=metadata if metadata else {})

    def log_completion(self, stats: dict):
        """Log final batch statistics."""
        self.log_progress("Geocoding Batch Complete", stats)
