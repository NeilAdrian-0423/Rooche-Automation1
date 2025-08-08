"""File monitoring service."""

import os
import time
import json
import logging
import threading
from datetime import datetime, timezone
from typing import Callable, Optional

class MonitoringService:
    def __init__(self, config_manager, audio_processor, webhook_service):
        self.config = config_manager
        self.audio_processor = audio_processor
        self.webhook_service = webhook_service
        self.monitoring_active = False
        self.monitoring_thread = None
        self.start_time = None
    
    def start_monitoring(self, after_dt: datetime, timeout_minutes: int,
                        notion_url: str, description: str,
                        callback: Callable, status_callback: Callable,
                        completion_callback: Callable):
        """Start monitoring for new audio/video uploads."""
        self.monitoring_active = True
        self.start_time = datetime.now()
        timeout_seconds = timeout_minutes * 60
        
        logging.debug(f"[Monitor] Starting monitoring with {timeout_minutes} minute timeout")
        logging.debug(f"[Monitor] Watching for uploads after {after_dt.isoformat()}")

        def monitoring_worker():
            start_monitor_time = time.time()
            last_display_time = 0
            
            while self.monitoring_active:
                current_time = time.time()
                elapsed_seconds = current_time - start_monitor_time
                
                if elapsed_seconds >= timeout_seconds:
                    self.monitoring_active = False
                    status_callback("⏰ Time limit reached - monitoring stopped")
                    completion_callback()
                    logging.debug("[Monitor] Timeout reached, stopping monitoring")
                    return
                
                remaining_seconds = int(timeout_seconds - elapsed_seconds)
                
                if int(current_time) != last_display_time:
                    last_display_time = int(current_time)
                    
                    hours = remaining_seconds // 3600
                    minutes = (remaining_seconds % 3600) // 60
                    seconds = remaining_seconds % 60
                    
                    if hours > 0:
                        time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
                    else:
                        time_str = f"{minutes:02d}:{seconds:02d}"
                    
                    status_callback(f"👀 Monitoring for uploads... {time_str} remaining")
                
                self._check_for_new_files(after_dt, notion_url, description, 
                                         callback, status_callback, completion_callback)
                time.sleep(1)
            
            if not self.monitoring_active:
                completion_callback()
        
        self.monitoring_thread = threading.Thread(target=monitoring_worker, daemon=True)
        self.monitoring_thread.start()
    
    def _check_for_new_files(self, after_dt, notion_url, description,
                            callback, status_callback, completion_callback):
        """Check ShareX history for new files."""
        history_path = self.config.get("history_path")
        if not history_path or not os.path.exists(history_path):
            return
        
        try:
            with open(history_path, 'r', encoding='utf-8') as f:
                content = f.read()

            raw_entries = "[" + content.replace("}\n{", "},\n{") + "]"
            history = json.loads(raw_entries)
            
            from core.constants import VALID_AUDIO_VIDEO_EXTENSIONS

            for entry in reversed(history):
                if not self.monitoring_active:
                    return
                    
                if "FilePath" in entry and "DateTime" in entry:
                    entry_time = datetime.fromisoformat(entry["DateTime"].replace("Z", "+00:00"))
                    if entry_time.tzinfo is None:
                        entry_time = entry_time.replace(tzinfo=timezone.utc)
                    
                    if entry_time > after_dt:
                        logging.debug(f"[Monitor] New file found: {entry['FileName']}")
                        file_name = entry.get("FileName", "").lower()
                        
                        if any(file_name.endswith(ext) for ext in VALID_AUDIO_VIDEO_EXTENSIONS):
                            self.monitoring_active = False
                            status_callback("🎬 Found audio/video file!")
                            
                            local_file_path = entry["FilePath"]
                            if os.path.exists(local_file_path):
                                transcription = self.audio_processor.process_file(local_file_path, status_callback)
                                if transcription:
                                    drive_url = entry.get("URL", "")
                                    self.webhook_service.send_data(
                                        notion_url, description, transcription, 
                                        drive_url, local_file_path
                                    )
                                    callback(transcription, drive_url, local_file_path)
                                    completion_callback()
                                else:
                                    status_callback("❌ File processing failed")
                                    completion_callback()
                            else:
                                status_callback(f"❌ File not found: {local_file_path}")
                                completion_callback()
                            return

        except Exception as e:
            logging.error(f"[Monitor] Error reading history: {e}")
            status_callback(f"⚠️ Error reading history: {str(e)}")
    
    def stop_monitoring(self):
        """Stop the monitoring process."""
        self.monitoring_active = False
        logging.debug("[Monitor] Monitoring stopped by user")