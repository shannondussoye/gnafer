"""Structured logging and health check pings."""

import logging
import sys
import uuid

from logtail import LogtailHandler
from pythonjsonlogger.json import JsonFormatter

from src.config import settings


class GeocoderObservability:
    def __init__(self, run_id: str | None = None):
        self.logtail_token = settings.logtail_token
        self.run_id = run_id or str(uuid.uuid4())

        # Setup Logger
        self.logger = logging.getLogger("gnafer")
        self.logger.setLevel(logging.INFO)

        # Clear existing handlers if re-initialized
        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        # Local console logging (Structured JSON)
        console_handler = logging.StreamHandler(sys.stdout)
        formatter = JsonFormatter(
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

    def log_progress(self, message: str, metadata: dict | None = None):
        """Log structured data with session tracking."""
        full_metadata = {"run_id": self.run_id}
        if metadata:
            full_metadata.update(metadata)
        self.logger.info(message, extra=full_metadata)

    def log_completion(self, stats: dict):
        """Log final batch statistics."""
        self.log_progress("Geocoding Batch Complete", stats)
