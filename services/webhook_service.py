"""Webhook communication service."""

import os
import logging
import requests
from typing import Optional
from dotenv import load_dotenv

load_dotenv()

class WebhookService:
    def __init__(self):
        self.webhook_url = os.getenv("WEBHOOK_URL", "").strip()
    
    def send_data(self, notion_url: str, description: str, 
                  transcription: Optional[str] = None,
                  drive_url: Optional[str] = None,
                  local_file_path: Optional[str] = None,
                  result: Optional[str] = None,
                  reason: Optional[str] = None) -> bool:
        """Send data to webhook."""
        if not self.webhook_url:
            logging.warning("[Webhook] No webhook URL configured in .env file.")
            return False

        logging.debug("[Webhook] Sending data to webhook...")
        data = {
            "notion_url": notion_url,
            "description": description,
        }
        
        if transcription is not None:
            data["transcription"] = transcription
        if drive_url is not None:
            data["drive_url"] = drive_url
        if local_file_path is not None:
            data["local_file_path"] = local_file_path
        if result is not None:
            data["result"] = result
        if reason is not None:
            data["reason"] = reason
        
        try:
            res = requests.post(self.webhook_url, json=data)
            res.raise_for_status()
            logging.debug("[Webhook] Sent successfully.")
            return True
        except Exception as e:
            logging.error(f"[Webhook] Failed to send: {e}")
            return False