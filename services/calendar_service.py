"""Calendar integration service."""

import os
import logging
import requests
from datetime import datetime, timezone
from typing import List, Dict, Any
from dotenv import load_dotenv

load_dotenv()

class CalendarService:
    def __init__(self):
        self.webhook_url = os.getenv("WEBHOOK_URL2", "").strip()
    
    def fetch_events(self) -> List[Dict[str, Any]]:
        """Fetch calendar events from the webhook."""
        try:
            if not self.webhook_url:
                logging.error("[Calendar] No webhook events URL configured")
                return []
            
            logging.debug(f"[Calendar] Fetching events from: {self.webhook_url}")
            response = requests.get(self.webhook_url, timeout=10)
            response.raise_for_status()
            
            events = response.json()
            if not isinstance(events, list):
                logging.error("[Calendar] Response is not a list")
                return []
            
            return self._process_events(events)
            
        except requests.RequestException as e:
            logging.error(f"[Calendar] Network error fetching events: {e}")
            return []
        except Exception as e:
            logging.error(f"[Calendar] Error fetching calendar events: {e}")
            return []
    
    def _process_events(self, events: List[Dict]) -> List[Dict[str, Any]]:
        """Process raw calendar events."""
        processed_events = []
        now = datetime.now(timezone.utc)
        
        for event in events:
            try:
                start_time_str = event['start']['dateTime']
                start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                local_start = start_time.astimezone()
                
                summary = event.get('summary', '')
                participant_name = self._extract_participant_name(summary)
                display_time = local_start.strftime("%I:%M %p")
                
                time_diff = start_time - now
                is_upcoming = 0 <= time_diff.total_seconds() <= 1800
                
                location = event.get('location', '').strip()
                
                processed_event = {
                    'id': event['id'],
                    'summary': summary,
                    'start_datetime': start_time,
                    'local_start': local_start,
                    'display_time': display_time,
                    'participant_name': participant_name,
                    'notion_url': event.get('description', '').strip(),
                    'location': location,
                    'meeting_link': (
                            location if location.startswith("http") or "://" in location
                            else f"https://{location}"
                        ) if location else "",
                    'is_upcoming': is_upcoming,
                    'time_until': time_diff.total_seconds() if time_diff.total_seconds() > 0 else 0,
                    'display_text': f"{local_start.strftime('%Y-%m-%d %I:%M %p')} - {summary}",
                    'auto_description': f"{display_time} {participant_name}".strip()
                }
                
                processed_events.append(processed_event)
                
            except Exception as e:
                logging.warning(f"[Calendar] Error processing event: {e}")
                continue
        
        processed_events.sort(key=lambda x: x['start_datetime'])
        logging.debug(f"[Calendar] Successfully processed {len(processed_events)} events")
        return processed_events

    
    def _extract_participant_name(self, summary: str) -> str:
        """Extract participant name from meeting summary."""
        try:
            if " with " in summary:
                parts = summary.split(" with ")
                if len(parts) > 1:
                    name_part = parts[1]
                    if "(" in name_part:
                        name_part = name_part.split("(")[0].strip()
                    return name_part.strip()
            
            if "(" in summary and ")" in summary:
                paren_content = summary[summary.find("(")+1:summary.find(")")]
                if paren_content and len(paren_content.split()) <= 3:
                    return paren_content
            
            words = summary.split()
            potential_names = []
            for word in words:
                if word.istitle() and len(word) > 2 and word not in ['Initial', 'Interview', 'Meeting', 'With']:
                    potential_names.append(word)
            
            if potential_names:
                return " ".join(potential_names[:2])
                
            return "Meeting"
            
        except Exception as e:
            logging.warning(f"[Calendar] Error extracting participant name: {e}")
            return "Meeting"