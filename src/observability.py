import os
import logging
import sys
import uuid
import urllib.request
from logtail import LogtailHandler
from pythonjsonlogger import jsonlogger
from dotenv import load_dotenv

load_dotenv()

class GeocoderObservability:
    def __init__(self, run_id: str = None):
        self.logtail_token = os.getenv("LOGTAIL_TOKEN")
        self.healthcheck_uuid = os.getenv("HEALTHCHECKS_UUID")
        self.run_id = run_id or str(uuid.uuid4())
        
        # Setup Logger
        self.logger = logging.getLogger("gnafer")
        self.logger.setLevel(logging.INFO)
        
        # Clear existing handlers if re-initialized
        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        # Local console logging (Structured JSON)
        console_handler = logging.StreamHandler(sys.stdout)
        formatter = jsonlogger.JsonFormatter(
            '%(asctime)s %(levelname)s %(name)s %(message)s',
            rename_fields={'asctime': 'timestamp', 'levelname': 'level'}
        )
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # Remote Recorder (Logtail)
        if self.logtail_token and "your_token" not in self.logtail_token:
            handler = LogtailHandler(source_token=self.logtail_token)
            self.logger.addHandler(handler)
            self.logger.info("Observability: Logtail Recorder initialized.", extra={"run_id": self.run_id})
        else:
            self.logger.info("Observability: Logtail disabled (no token).", extra={"run_id": self.run_id})

    def log_progress(self, message: str, metadata: dict = None):
        """Log structured data with session tracking."""
        full_metadata = {"run_id": self.run_id}
        if metadata:
            full_metadata.update(metadata)
        self.logger.info(message, extra=full_metadata)

    def log_completion(self, stats: dict):
        """Log final batch statistics."""
        self.log_progress("Geocoding Batch Complete", stats)

    def ping_healthcheck(self, suffix: str = ""):
        """Ping Healthchecks.io. suffix can be '/fail' or '/start'."""
        if not self.healthcheck_uuid or "your_uuid" in self.healthcheck_uuid:
            return
        try:
            url = f"https://hc-ping.com/{self.healthcheck_uuid}{suffix}"
            urllib.request.urlopen(url, timeout=10)
        except Exception:
            self.logger.warning("Healthchecks.io ping failed", extra={"run_id": self.run_id})

