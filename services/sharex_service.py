"""ShareX integration service."""

import logging
import subprocess
import platform
import time
import os
from typing import Optional, List, Dict, Any
import json
from datetime import datetime, timezone, timedelta

try:
    from pynput.keyboard import Key, Controller
    keyboard_controller = Controller()
    PYNPUT_AVAILABLE = True
except ImportError:
    PYNPUT_AVAILABLE = False
    print("Warning: pynput not installed. ShareX keyboard shortcuts will not work.")
    print("Install with: pip install pynput")

class ShareXService:
    def __init__(self, config_manager):
        self.config = config_manager
    
    def launch_sharex(self) -> bool:
        """Launch ShareX application."""
        try:
            if platform.system() == "Windows":
                # Try to find ShareX in PATH first
                try:
                    subprocess.Popen(["ShareX.exe"], shell=True)
                    logging.info("[ShareX] Launched ShareX from PATH")
                    time.sleep(2)  # Give ShareX time to start
                    return True
                except:
                    pass
                
                # Try common ShareX installation paths
                paths_to_try = [
                    r"C:\Program Files\ShareX\ShareX.exe",
                    r"C:\Program Files (x86)\ShareX\ShareX.exe",
                    os.path.expanduser(r"~\AppData\Local\ShareX\ShareX.exe"),
                    os.path.expanduser(r"~\scoop\apps\sharex\current\ShareX.exe"),  # Scoop installation
                    r"C:\ProgramData\chocolatey\lib\sharex\tools\ShareX\ShareX.exe",  # Chocolatey
                ]
                
                # Try known installation paths
                for path in paths_to_try:
                    if os.path.exists(path):
                        subprocess.Popen([path])
                        logging.info(f"[ShareX] Launched ShareX from {path}")
                        time.sleep(2)  # Give ShareX time to start
                        return True
                
                # Try using Windows start menu search
                try:
                    subprocess.Popen('start "" "ShareX"', shell=True)
                    logging.info("[ShareX] Launched ShareX via Windows start")
                    time.sleep(2)
                    return True
                except:
                    pass
                
                logging.warning("[ShareX] Could not find ShareX executable")
                return False
            else:
                logging.warning("[ShareX] ShareX launch only supported on Windows")
                return False
        except Exception as e:
            logging.error(f"[ShareX] Error launching ShareX: {e}")
            return False
    
    def trigger_recording(self) -> bool:
        """Trigger ShareX screen recording with Shift + Print Screen."""
        if not PYNPUT_AVAILABLE:
            logging.error("[ShareX] pynput not available - cannot send keyboard shortcuts")
            return False
        
        try:
            # First ensure ShareX is running
            self.launch_sharex()
            
            logging.debug("[ShareX] Triggering screen recording (Shift + Print Screen)")
            
            # Small delay to ensure ShareX is ready
            time.sleep(0.5)
            
            keyboard_controller.press(Key.shift)
            keyboard_controller.press(Key.print_screen)
            keyboard_controller.release(Key.print_screen)
            keyboard_controller.release(Key.shift)
            
            logging.debug("[ShareX] Screen recording shortcut sent successfully")
            return True
            
        except Exception as e:
            logging.error(f"[ShareX] Error sending screen recording shortcut: {e}")
            return False
    
    def stop_recording(self) -> bool:
        """Stop ShareX screen recording."""
        return self.trigger_recording()  # Same shortcut toggles
    
    def get_recent_files(self, hours_back: int = 24) -> List[Dict[str, Any]]:
        """Get recent audio/video files from ShareX history."""
        history_path = self.config.get("history_path")
        if not history_path or not os.path.exists(history_path):
            return []
        
        try:
            with open(history_path, 'r', encoding='utf-8') as f:
                content = f.read()

            raw_entries = "[" + content.replace("}\n{", "},\n{") + "]"
            history = json.loads(raw_entries)
            
            cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
            audio_video_files = []
            
            from core.constants import VALID_AUDIO_VIDEO_EXTENSIONS
            
            for entry in reversed(history):
                if "FilePath" in entry and "DateTime" in entry and "FileName" in entry:
                    try:
                        entry_time = datetime.fromisoformat(entry["DateTime"].replace("Z", "+00:00"))
                        if entry_time.tzinfo is None:
                            entry_time = entry_time.replace(tzinfo=timezone.utc)
                        
                        if entry_time > cutoff_time:
                            file_name = entry.get("FileName", "").lower()
                            if any(file_name.endswith(ext) for ext in VALID_AUDIO_VIDEO_EXTENSIONS):
                                local_time = entry_time.astimezone()
                                time_str = local_time.strftime("%Y-%m-%d %I:%M:%S %p")
                                
                                audio_video_files.append({
                                    'filename': entry.get("FileName", "Unknown"),
                                    'filepath': entry.get("FilePath", ""),
                                    'url': entry.get("URL", ""),
                                    'datetime': entry_time,
                                    'display_time': time_str,
                                    'display_text': f"{time_str} - {entry.get('FileName', 'Unknown')}"
                                })
                    except Exception as e:
                        logging.warning(f"[History] Error parsing entry: {e}")
                        continue
            
            return audio_video_files[:20]
            
        except Exception as e:
            logging.error(f"[History] Error reading history: {e}")
            return []