import json
import time
import os
import threading
from datetime import datetime, timezone, timedelta
import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import requests
import tempfile
import subprocess
import logging
from transcribe_anything import transcribe_anything
from typing import Optional
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Set up logging
logging.basicConfig(
    filename="logs.txt",
    filemode="a",
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(message)s",
)

# Also log to console
console = logging.StreamHandler()
console.setLevel(logging.DEBUG)
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
console.setFormatter(formatter)
logging.getLogger().addHandler(console)

CONFIG_FILE = "config.json"
config = {
    "history_path": None,
    "whisper_model": "base",
    "whisper_device": "cpu",
    "wait_timer_minutes": 60,
    "webhook_events_url": "https://n8n.roochedigital.com/webhook/get-events"
}

# Global variables for monitoring control
monitoring_active = False
monitoring_thread = None
start_time = None


def save_config():
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f)


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                loaded = json.load(f)
                config.update(loaded)
        except Exception as e:
            print(f"[Config] Failed to load config: {e}")


def fetch_calendar_events():
    """Fetch calendar events from the webhook"""
    try:
        webhook_url = config.get("webhook_events_url", "")
        if not webhook_url:
            logging.error("[Calendar] No webhook events URL configured")
            return []
        
        logging.debug(f"[Calendar] Fetching events from: {webhook_url}")
        response = requests.get(webhook_url, timeout=10)
        response.raise_for_status()
        
        events = response.json()
        if not isinstance(events, list):
            logging.error("[Calendar] Response is not a list")
            return []
        
        # Process and sort events
        processed_events = []
        now = datetime.now(timezone.utc)
        
        for event in events:
            try:
                # Parse start time
                start_time_str = event['start']['dateTime']
                start_time = datetime.fromisoformat(start_time_str.replace('Z', '+00:00'))
                
                # Convert to local time for display
                local_start = start_time.astimezone()
                
                # Extract participant name from summary (assumes format like "Initial: 25min with Jing (Geraldo Tolentino)")
                summary = event.get('summary', '')
                participant_name = extract_participant_name(summary)
                
                # Create display time
                display_time = local_start.strftime("%I:%M %p")  # e.g., "1:30 PM"
                
                # Determine if this is an upcoming meeting (within next 30 minutes)
                time_diff = start_time - now
                is_upcoming = 0 <= time_diff.total_seconds() <= 1800  # 30 minutes = 1800 seconds
                
                processed_event = {
                    'id': event['id'],
                    'summary': summary,
                    'start_datetime': start_time,
                    'local_start': local_start,
                    'display_time': display_time,
                    'participant_name': participant_name,
                    'notion_url': event.get('description', '').strip(),
                    'location': event.get('location', ''),
                    'is_upcoming': is_upcoming,
                    'time_until': time_diff.total_seconds() if time_diff.total_seconds() > 0 else 0,
                    'display_text': f"{local_start.strftime('%Y-%m-%d %I:%M %p')} - {summary}",
                    'auto_description': f"{display_time} {participant_name}".strip()
                }
                
                processed_events.append(processed_event)
                
            except Exception as e:
                logging.warning(f"[Calendar] Error processing event: {e}")
                continue
        
        # Sort events by start time
        processed_events.sort(key=lambda x: x['start_datetime'])
        
        logging.debug(f"[Calendar] Successfully processed {len(processed_events)} events")
        return processed_events
        
    except requests.RequestException as e:
        logging.error(f"[Calendar] Network error fetching events: {e}")
        return []
    except Exception as e:
        logging.error(f"[Calendar] Error fetching calendar events: {e}")
        return []


def extract_participant_name(summary):
    """Extract participant name from meeting summary"""
    try:
        # Look for patterns like "with [Name]" or "[Name] (" 
        if " with " in summary:
            # Pattern: "Initial: 25min with Jing (Geraldo Tolentino)"
            parts = summary.split(" with ")
            if len(parts) > 1:
                name_part = parts[1]
                # Remove parenthetical parts
                if "(" in name_part:
                    name_part = name_part.split("(")[0].strip()
                return name_part.strip()
        
        # Alternative pattern: look for name before parentheses
        if "(" in summary and ")" in summary:
            # Try to extract name from parentheses as fallback
            paren_content = summary[summary.find("(")+1:summary.find(")")]
            if paren_content and len(paren_content.split()) <= 3:  # Reasonable name length
                return paren_content
        
        # If no specific pattern found, try to extract from summary
        # Look for capitalized words that might be names
        words = summary.split()
        potential_names = []
        for word in words:
            if word.istitle() and len(word) > 2 and word not in ['Initial', 'Interview', 'Meeting', 'With']:
                potential_names.append(word)
        
        if potential_names:
            return " ".join(potential_names[:2])  # Take first two capitalized words
            
        return "Meeting"  # Default fallback
        
    except Exception as e:
        logging.warning(f"[Calendar] Error extracting participant name: {e}")
        return "Meeting"


def refresh_calendar_events(listbox, refresh_button, ui_elements):
    """Refresh the calendar events list"""
    refresh_button.config(text="Refreshing...", state=tk.DISABLED)
    
    def refresh_worker():
        try:
            # Clear current list
            listbox.delete(0, tk.END)
            
            # Fetch events
            events = fetch_calendar_events()
            
            if events:
                for event in events:
                    display_text = event['display_text']
                    
                    # Highlight upcoming meetings
                    if event['is_upcoming']:
                        minutes_until = int(event['time_until'] / 60)
                        display_text += f" [STARTING IN {minutes_until} MIN!]"
                    
                    listbox.insert(tk.END, display_text)
                
                # Store event data
                listbox.event_data = events
                
                # Auto-select the most upcoming meeting if within 30 minutes
                upcoming_events = [i for i, event in enumerate(events) if event['is_upcoming']]
                if upcoming_events:
                    # Select the first upcoming event
                    listbox.selection_set(upcoming_events[0])
                    listbox.see(upcoming_events[0])  # Scroll to show the selection
                    # Auto-fill the form
                    auto_fill_from_selection(listbox, ui_elements)
                
            else:
                listbox.insert(tk.END, "No calendar events found")
                listbox.event_data = []
            
        except Exception as e:
            logging.error(f"[Calendar] Error refreshing events: {e}")
            listbox.delete(0, tk.END)
            listbox.insert(tk.END, f"Error loading events: {str(e)}")
            listbox.event_data = []
        finally:
            refresh_button.config(text="Refresh Events", state=tk.NORMAL)
    
    # Run in thread to avoid blocking UI
    thread = threading.Thread(target=refresh_worker, daemon=True)
    thread.start()


def auto_fill_from_selection(listbox, ui_elements):
    """Auto-fill form fields based on selected calendar event"""
    selection = listbox.curselection()
    if not selection or not hasattr(listbox, 'event_data') or not listbox.event_data:
        return
    
    selected_index = selection[0]
    if selected_index >= len(listbox.event_data):
        return
    
    event = listbox.event_data[selected_index]
    
    # Auto-fill Notion URL (from description)
    notion_url = extract_notion_url(event['notion_url'])
    ui_elements['notion_entry'].delete(0, tk.END)
    ui_elements['notion_entry'].insert(0, notion_url)
    
    # Auto-fill description (time + participant name)
    ui_elements['description_entry'].delete(0, tk.END)
    ui_elements['description_entry'].insert(0, event['auto_description'])


def extract_notion_url(description_text):
    """Extract Notion page ID from p= parameter or URL structure"""
    if not description_text:
        return ""
    
    import re
    
    # Remove HTML tags and decode entities
    clean_text = description_text.replace('<a href="', '').replace('">', '').replace('</a>', '')
    clean_text = clean_text.replace('&amp;', '&')
    
    logging.debug(f"[URL Extract] Processing description: {clean_text[:150]}...")
    
    # Find Notion URLs first
    notion_url_patterns = [
        r'https://www\.notion\.so/[^\s<>"]+',
        r'https://notion\.so/[^\s<>"]+',
    ]
    
    notion_url = None
    for pattern in notion_url_patterns:
        matches = re.findall(pattern, clean_text)
        if matches:
            # Get the last/longest match
            notion_url = matches[-1]
            logging.debug(f"[URL Extract] Found Notion URL: {notion_url}")
            break
    
    if notion_url:
        # First priority: Look for p= parameter (this contains the actual page ID)
        p_param_match = re.search(r'[?&]p=([a-f0-9]{32})', notion_url, re.IGNORECASE)
        if p_param_match:
            page_id = p_param_match.group(1)
            clean_url = f"https://www.notion.so/{page_id}"
            logging.debug(f"[URL Extract] Found page ID in p= parameter: {page_id}")
            logging.debug(f"[URL Extract] Created clean Notion URL: {clean_url}")
            return clean_url
        
        # Second priority: Look for page ID directly in path (like /rooche/32chars)
        path_match = re.search(r'/[^/]+/([a-f0-9]{32})', notion_url, re.IGNORECASE)
        if path_match:
            page_id = path_match.group(1)
            clean_url = f"https://www.notion.so/{page_id}"
            logging.debug(f"[URL Extract] Found page ID in URL path: {page_id}")
            logging.debug(f"[URL Extract] Created clean Notion URL: {clean_url}")
            return clean_url
        
        # Third priority: Any 32-char hex string in the URL (use the first one found)
        hex_matches = re.findall(r'[a-f0-9]{32}', notion_url, re.IGNORECASE)
        if hex_matches:
            # Use the first one found (usually the main page ID)
            page_id = hex_matches[0]
            clean_url = f"https://www.notion.so/{page_id}"
            logging.debug(f"[URL Extract] Found page ID as first hex string: {page_id}")
            logging.debug(f"[URL Extract] Created clean Notion URL: {clean_url}")
            return clean_url
    
    # Final fallback: look for any 32-character hex string in the entire text
    hex_pattern = r'[a-f0-9]{32}'
    hex_matches = re.findall(hex_pattern, clean_text, re.IGNORECASE)
    
    if hex_matches:
        # Use the first one found
        page_id = hex_matches[0]
        clean_url = f"https://www.notion.so/{page_id}"
        logging.debug(f"[URL Extract] Final fallback: Created clean Notion URL: {clean_url}")
        return clean_url
    
    logging.warning(f"[URL Extract] No valid Notion page ID found in: {clean_text}")
    return clean_text.strip()


def extract_audio(file_path, status_callback):
    """Extract audio from video/audio file and return path to extracted audio"""
    status_callback("🎧 Extracting audio from file...")
    logging.debug(f"[Audio] Starting audio extraction from: {file_path}")
    
    temp_audio_path = tempfile.mktemp(suffix=".wav")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", file_path, "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1", temp_audio_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True
        )
        
        if os.path.exists(temp_audio_path):
            logging.debug(f"[Audio] Audio extracted successfully to: {temp_audio_path}")
            status_callback("✅ Audio extraction completed!")
            return temp_audio_path
        else:
            logging.error("[Audio] Audio file not created")
            status_callback("❌ Audio extraction failed - no output file")
            return None
            
    except subprocess.CalledProcessError as e:
        logging.error(f"[Audio] Error extracting audio: {e.stderr.decode()}")
        status_callback(f"❌ Audio extraction failed: {e.stderr.decode()}")
        return None
    except Exception as e:
        logging.error(f"[Audio] Unexpected error during audio extraction: {e}")
        status_callback(f"❌ Audio extraction failed: {str(e)}")
        return None


def transcribe_locally(audio_file_path: str, status_callback) -> Optional[str]:
    """Transcribe audio file using local Whisper model"""
    try:
        status_callback("🎯 Starting local transcription...")
        logging.debug(f"[Whisper] Starting transcription of: {audio_file_path}")
        
        if not os.path.exists(audio_file_path):
            status_callback("❌ Audio file not found")
            return None
            
        file_size = os.path.getsize(audio_file_path)
        logging.debug(f"[Whisper] Audio file size: {file_size} bytes")

        output_dir = tempfile.mkdtemp()
        logging.debug(f"[Whisper] Using temporary directory: {output_dir}")

        try:
            transcribe_anything(
                url_or_file=audio_file_path,
                output_dir=output_dir,
                task="transcribe",
                model=config.get("whisper_model", "base"),
                device=config.get("whisper_device", "cpu"),
                language=None
            )
            
            base_name = "out"
            output_txt = os.path.join(output_dir, f"{base_name}.txt")
            
            if os.path.exists(output_txt):
                with open(output_txt, "r", encoding="utf-8") as f:
                    transcription_text = f.read()
                
                status_callback("✅ Transcription completed!")
                logging.debug(f"[Whisper] Transcription completed successfully: {transcription_text[:100]}...")
                return transcription_text
            else:
                status_callback("❌ Transcription output not found")
                logging.error("[Whisper] No output text file found")
                return None
                
        except Exception as e:
            logging.error(f"[Whisper] Transcription failed: {e}")
            status_callback(f"❌ Local transcription failed: {str(e)}")
            return None
            
    except Exception as e:
        logging.error(f"[Whisper] Transcription process failed: {e}")
        status_callback(f"❌ Local transcription failed: {str(e)}")
        return None


def process_audio_file(file_path, status_callback):
    """Process audio/video file: extract audio first, then transcribe"""
    try:
        audio_path = extract_audio(file_path, status_callback)
        if not audio_path or not os.path.exists(audio_path):
            status_callback("❌ Failed to extract audio")
            return None

        transcription = transcribe_locally(audio_path, status_callback)
        
        try:
            if os.path.exists(audio_path):
                os.remove(audio_path)
                logging.debug(f"[Cleanup] Removed temporary audio file: {audio_path}")
        except Exception as e:
            logging.warning(f"[Cleanup] Failed to remove temporary file: {e}")

        return transcription
        
    except Exception as e:
        logging.error(f"[Process] Error processing audio file: {e}")
        status_callback(f"❌ Error processing file: {str(e)}")
        return None


def get_recent_audio_video_files(hours_back=24):
    """Get recent audio/video files from ShareX history"""
    if not config.get("history_path") or not os.path.exists(config["history_path"]):
        return []
    
    try:
        with open(config["history_path"], 'r', encoding='utf-8') as f:
            content = f.read()

        raw_entries = "[" + content.replace("}\n{", "},\n{") + "]"
        history = json.loads(raw_entries)
        
        cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
        audio_video_files = []
        
        valid_ext = ['.mp3', '.mp4', '.wav', '.m4a', '.flac', '.ogg', '.webm', '.avi', '.mov', '.wmv']
        
        for entry in reversed(history):
            if "FilePath" in entry and "DateTime" in entry and "FileName" in entry:
                try:
                    entry_time = datetime.fromisoformat(entry["DateTime"].replace("Z", "+00:00"))
                    if entry_time.tzinfo is None:
                        entry_time = entry_time.replace(tzinfo=timezone.utc)
                    
                    if entry_time > cutoff_time:
                        file_name = entry.get("FileName", "").lower()
                        if any(file_name.endswith(ext) for ext in valid_ext):
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


def stop_monitoring(status_callback, ui_elements):
    """Stop the monitoring process and re-enable UI"""
    global monitoring_active
    monitoring_active = False
    status_callback("🛑 Monitoring stopped")
    logging.debug("[Monitor] Monitoring stopped by user or timer")
    
    enable_ui_elements(ui_elements, True)


def enable_ui_elements(ui_elements, enable=True):
    """Enable or disable UI elements"""
    state = tk.NORMAL if enable else tk.DISABLED
    
    ui_elements['notion_entry'].config(state=state)
    ui_elements['description_entry'].config(state=state)
    ui_elements['timer_entry'].config(state=state)
    ui_elements['model_entry'].config(state=state)
    ui_elements['device_entry'].config(state=state)
    ui_elements['submit_button'].config(state=state)
    ui_elements['select_button'].config(state=state)
    
    ui_elements['reset_button'].config(state=tk.DISABLED if enable else tk.NORMAL)


def wait_for_audio_video_upload_with_timeout(after_dt: datetime, timeout_minutes: int, callback, status_callback, ui_elements):
    """Wait for audio/video upload with a timeout"""
    global monitoring_active, start_time
    
    monitoring_active = True
    start_time = datetime.now()
    timeout_seconds = timeout_minutes * 60
    
    logging.debug(f"[Monitor] Starting monitoring with {timeout_minutes} minute timeout")
    logging.debug(f"[Monitor] Watching for uploads after {after_dt.isoformat()}")

    def monitoring_worker():
        global monitoring_active
        start_monitor_time = time.time()
        last_display_time = 0
        
        while monitoring_active:
            current_time = time.time()
            elapsed_seconds = current_time - start_monitor_time
            
            if elapsed_seconds >= timeout_seconds:
                monitoring_active = False
                status_callback("⏰ Time limit reached - monitoring stopped")
                enable_ui_elements(ui_elements, True)
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
            
            try:
                with open(config["history_path"], 'r', encoding='utf-8') as f:
                    content = f.read()

                raw_entries = "[" + content.replace("}\n{", "},\n{") + "]"
                history = json.loads(raw_entries)

                for entry in reversed(history):
                    if not monitoring_active:
                        return
                        
                    if "FilePath" in entry and "DateTime" in entry:
                        entry_time = datetime.fromisoformat(entry["DateTime"].replace("Z", "+00:00"))
                        if entry_time.tzinfo is None:
                            entry_time = entry_time.replace(tzinfo=timezone.utc)
                        if entry_time > after_dt:
                            logging.debug(f"[Monitor] New file found: {entry['FileName']}")
                            file_name = entry.get("FileName", "").lower()
                            valid_ext = ['.mp3', '.mp4', '.wav', '.m4a', '.flac', '.ogg', '.webm', '.avi', '.mov', '.wmv']
                            if any(file_name.endswith(ext) for ext in valid_ext):
                                monitoring_active = False
                                status_callback("🎬 Found audio/video file!")
                                
                                local_file_path = entry["FilePath"]
                                if os.path.exists(local_file_path):
                                    transcription = process_audio_file(local_file_path, status_callback)
                                    if transcription:
                                        drive_url = entry.get("URL", "")
                                        callback(transcription, drive_url, local_file_path)
                                        enable_ui_elements(ui_elements, True)
                                        return
                                    else:
                                        status_callback("❌ File processing failed")
                                        enable_ui_elements(ui_elements, True)
                                        return
                                else:
                                    status_callback(f"❌ File not found: {local_file_path}")
                                    enable_ui_elements(ui_elements, True)
                                    return
                            else:
                                logging.debug(f"[Monitor] Ignoring non-audio/video file: {file_name}")
                                continue

            except Exception as e:
                logging.error(f"[Monitor] Error reading history: {e}")
                status_callback(f"⚠️ Error reading history: {str(e)}")

            time.sleep(1)
        
        if not monitoring_active:
            enable_ui_elements(ui_elements, True)
    
    global monitoring_thread
    monitoring_thread = threading.Thread(target=monitoring_worker, daemon=True)
    monitoring_thread.start()


def send_to_webhook(notion_url, description, transcription, drive_url, local_file_path):
    webhook_url = os.getenv("WEBHOOK_URL", "").strip()
    if not webhook_url:
        logging.warning("[Webhook] No webhook URL configured in .env file.")
        return

    logging.debug("[Webhook] Sending transcription data...")
    data = {
        "notion_url": notion_url,
        "description": description,
        "transcription": transcription,
        "drive_url": drive_url,
        "local_file_path": local_file_path
    }
    try:
        res = requests.post(webhook_url, json=data)
        res.raise_for_status()
        logging.debug("[Webhook] Sent successfully.")
    except Exception as e:
        logging.error(f"[Webhook] Failed to send: {e}")


def handle_submission(ui_elements, status_label):
    notion_url = ui_elements['notion_entry'].get().strip()
    description = ui_elements['description_entry'].get().strip()

    if not notion_url or not description:
        messagebox.showerror("Error", "Please enter both Notion URL and description.")
        return

    if not config.get("history_path"):
        messagebox.showerror("Error", "No ShareX history.json selected.")
        return

    webhook_url = os.getenv("WEBHOOK_URL", "").strip()
    if not webhook_url:
        messagebox.showerror("Error", "Webhook URL not set in .env file.")
        return

    try:
        wait_minutes = int(ui_elements['timer_entry'].get().strip())
        if wait_minutes <= 0:
            messagebox.showerror("Error", "Time limit must be greater than 0 minutes.")
            return
        config["wait_timer_minutes"] = wait_minutes
        save_config()
    except ValueError:
        messagebox.showerror("Error", "Please enter a valid number for time limit.")
        return

    submit_time = datetime.now(timezone.utc).astimezone()
    
    config["whisper_model"] = ui_elements['model_entry'].get().strip()
    config["whisper_device"] = ui_elements['device_entry'].get().strip()
    save_config()
    
    enable_ui_elements(ui_elements, False)
    
    def on_transcription_complete(transcription, drive_url, local_file_path):
        send_to_webhook(notion_url, description, transcription, drive_url, local_file_path)
        status_label.config(text="✅ Transcription sent to webhook!")

    def status_update(message):
        status_label.config(text=message)

    status_update(f"🚀 Starting monitoring with {wait_minutes} minute time limit...")
    
    wait_for_audio_video_upload_with_timeout(
        submit_time, 
        wait_minutes, 
        on_transcription_complete, 
        status_update,
        ui_elements
    )


def select_history_file(label, submit_button):
    path = filedialog.askopenfilename(
        title="Select ShareX history.json",
        filetypes=[("JSON Files", "*.json")],
        initialfile="history.json"
    )
    if path:
        config["history_path"] = path
        label.config(text=f"Selected: {os.path.basename(path)}")
        update_submit_button_state(submit_button)
        save_config()


def update_submit_button_state(submit_button):
    if config.get("history_path") and os.getenv("WEBHOOK_URL", "").strip():
        submit_button.config(state=tk.NORMAL)
    else:
        submit_button.config(state=tk.DISABLED)


def create_gui():
    load_config()

    root = tk.Tk()
    root.title("Calendar-Integrated ShareX Monitor")
    root.geometry("700x900")

    # Create notebook for tabs
    notebook = ttk.Notebook(root)
    notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    # Tab 1: Calendar Events
    calendar_frame = ttk.Frame(notebook)
    notebook.add(calendar_frame, text="📅 Calendar Events")

    tk.Label(calendar_frame, text="Upcoming Calendar Events:", font=("Arial", 12, "bold")).pack(pady=(10, 5))

    # Calendar events listbox
    cal_listbox_frame = tk.Frame(calendar_frame)
    cal_listbox_frame.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)

    cal_scrollbar = tk.Scrollbar(cal_listbox_frame)
    cal_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    cal_listbox = tk.Listbox(cal_listbox_frame, yscrollcommand=cal_scrollbar.set, height=10, font=("Arial", 9))
    cal_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    cal_scrollbar.config(command=cal_listbox.yview)

    # Calendar refresh button
    cal_refresh_button = tk.Button(
        calendar_frame,
        text="🔄 Refresh Calendar Events",
        bg="#2196F3",
        fg="white",
        font=("Arial", 10)
    )
    cal_refresh_button.pack(pady=5)

    # Auto-filled form section
    form_frame = tk.LabelFrame(calendar_frame, text="Meeting Details (Auto-filled)", font=("Arial", 10, "bold"))
    form_frame.pack(fill=tk.X, padx=10, pady=10)

    tk.Label(form_frame, text="Notion URL:").pack(pady=(10, 0))
    notion_entry = tk.Entry(form_frame, width=80, font=("Arial", 9))
    notion_entry.pack(pady=5)

    tk.Label(form_frame, text="Description:").pack()
    description_entry = tk.Entry(form_frame, width=80, font=("Arial", 9))
    description_entry.pack(pady=5)

    # Configuration section
    config_frame = tk.LabelFrame(calendar_frame, text="Configuration", font=("Arial", 10, "bold"))
    config_frame.pack(fill=tk.X, padx=10, pady=10)

    tk.Label(config_frame, text="Time Limit (minutes):").pack()
    timer_entry = tk.Entry(config_frame, width=20)
    timer_entry.insert(0, str(config.get("wait_timer_minutes", 60)))
    timer_entry.pack(pady=2)

    tk.Label(config_frame, text="Whisper Model:").pack()
    model_entry = tk.Entry(config_frame, width=20)
    model_entry.insert(0, config.get("whisper_model", "base"))
    model_entry.pack(pady=2)

    tk.Label(config_frame, text="Device:").pack()
    device_entry = tk.Entry(config_frame, width=20)
    device_entry.insert(0, config.get("whisper_device", "cpu"))
    device_entry.pack(pady=2)

    status_label = tk.Label(calendar_frame, text="", fg="blue", wraplength=680, font=("Arial", 10))
    status_label.pack(pady=10)

    file_label = tk.Label(calendar_frame, text="No ShareX history file selected", fg="gray")
    file_label.pack()

    # Control buttons
    button_frame = tk.Frame(calendar_frame)
    button_frame.pack(pady=10)

    select_button = tk.Button(
        button_frame,
        text="📁 Select ShareX History",
        command=lambda: select_history_file(file_label, submit_button)
    )
    select_button.pack(side=tk.LEFT, padx=5)

    submit_button = tk.Button(
        button_frame,
        text="🚀 Start Monitoring",
        state=tk.DISABLED,
        bg="#4CAF50",
        fg="white",
        font=("Arial", 10, "bold")
    )
    submit_button.pack(side=tk.LEFT, padx=5)

    reset_button = tk.Button(
        button_frame,
        text="🛑 Stop Monitoring",
        state=tk.DISABLED,
        bg="#FF5722",
        fg="white",
        font=("Arial", 9)
    )
    reset_button.pack(side=tk.LEFT, padx=5)

    # Tab 2: Manual Selection (existing functionality)
    manual_frame = ttk.Frame(notebook)
    notebook.add(manual_frame, text="📁 Manual Files")

    tk.Label(manual_frame, text="Recent Audio/Video Files (Last 24 Hours):", font=("Arial", 12, "bold")).pack(pady=(10, 5))

    # Create listbox with scrollbar for manual files
    manual_listbox_frame = tk.Frame(manual_frame)
    manual_listbox_frame.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)

    manual_scrollbar = tk.Scrollbar(manual_listbox_frame)
    manual_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

    manual_listbox = tk.Listbox(manual_listbox_frame, yscrollcommand=manual_scrollbar.set, height=15, font=("Arial", 9))
    manual_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    manual_scrollbar.config(command=manual_listbox.yview)

    # Manual refresh button
    manual_refresh_button = tk.Button(
        manual_frame,
        text="🔄 Refresh File List",
        bg="#2196F3",
        fg="white",
        font=("Arial", 9)
    )
    manual_refresh_button.pack(pady=5)

    # Process selected button
    process_selected_button = tk.Button(
        manual_frame,
        text="🎯 Process Selected File",
        state=tk.DISABLED,
        bg="#FF9800",
        fg="white",
        font=("Arial", 10, "bold")
    )
    process_selected_button.pack(pady=10)

    manual_info_label = tk.Label(
        manual_frame,
        text="Use this tab if you forgot to start monitoring before uploading.\n"
             "Select a recent file and click 'Process Selected File' to transcribe\n"
             "and send it to your webhook. Make sure to fill in the meeting details\n"
             "in the Calendar Events tab first.",
        fg="gray",
        font=("Arial", 8),
        wraplength=680
    )
    manual_info_label.pack(pady=10)

    # Info section
    info_frame = tk.LabelFrame(calendar_frame, text="ℹ️ How to Use", font=("Arial", 10, "bold"))
    info_frame.pack(fill=tk.X, padx=10, pady=5)

    info_text = tk.Label(
        info_frame,
        text="1. Click 'Refresh Calendar Events' to load your meetings\n"
             "2. Select a meeting from the list (upcoming meetings are highlighted)\n" 
             "3. Notion URL and description will auto-fill\n"
             "4. Click 'Start Monitoring' to watch for ShareX uploads\n"
             "5. When you upload an audio/video file, it will auto-transcribe and send to your webhook\n\n"
             "⚡ Meetings starting within 30 minutes are automatically highlighted and selected!",
        fg="gray",
        font=("Arial", 8),
        justify=tk.LEFT,
        wraplength=680
    )
    info_text.pack(pady=10)

    # Create UI elements dictionary
    ui_elements = {
        'notion_entry': notion_entry,
        'description_entry': description_entry,
        'timer_entry': timer_entry,
        'model_entry': model_entry,
        'device_entry': device_entry,
        'submit_button': submit_button,
        'select_button': select_button,
        'reset_button': reset_button,
        'process_selected_button': process_selected_button
    }

    # Configure button commands
    cal_refresh_button.config(
        command=lambda: refresh_calendar_events(cal_listbox, cal_refresh_button, ui_elements)
    )
    
    manual_refresh_button.config(
        command=lambda: refresh_file_list(manual_listbox, manual_refresh_button)
    )
    
    reset_button.config(
        command=lambda: stop_monitoring(lambda msg: status_label.config(text=msg), ui_elements)
    )
    
    submit_button.config(
        command=lambda: handle_submission(ui_elements, status_label)
    )
    
    process_selected_button.config(
        command=lambda: process_selected_file(manual_listbox, ui_elements, status_label)
    )

    # Event handlers
    def on_calendar_select(event):
        auto_fill_from_selection(cal_listbox, ui_elements)
    
    def on_manual_file_select(event):
        if manual_listbox.curselection() and hasattr(manual_listbox, 'file_data') and manual_listbox.file_data:
            process_selected_button.config(state=tk.NORMAL)
        else:
            process_selected_button.config(state=tk.DISABLED)
    
    cal_listbox.bind('<<ListboxSelect>>', on_calendar_select)
    manual_listbox.bind('<<ListboxSelect>>', on_manual_file_select)

    # Configuration update handlers
    timer_entry.bind("<FocusOut>", lambda e: update_wait_timer(timer_entry))
    timer_entry.bind("<KeyRelease>", lambda e: update_wait_timer(timer_entry))
    model_entry.bind("<FocusOut>", lambda e: update_whisper_model(model_entry))
    device_entry.bind("<FocusOut>", lambda e: update_whisper_device(device_entry))

    # Initialize
    if config.get("history_path") and os.path.exists(config["history_path"]):
        file_label.config(text=f"Selected: {os.path.basename(config['history_path'])}")

    update_submit_button_state(submit_button)

    # Auto-load calendar events on startup
    root.after(1000, lambda: refresh_calendar_events(cal_listbox, cal_refresh_button, ui_elements))

    root.mainloop()


def refresh_file_list(listbox, refresh_button):
    """Refresh the list of recent audio/video files"""
    refresh_button.config(text="Refreshing...", state=tk.DISABLED)
    
    # Clear current list
    listbox.delete(0, tk.END)
    
    # Get recent files
    recent_files = get_recent_audio_video_files()
    
    if recent_files:
        for file_info in recent_files:
            listbox.insert(tk.END, file_info['display_text'])
        
        # Store file info as listbox data
        listbox.file_data = recent_files
    else:
        listbox.insert(tk.END, "No recent audio/video files found")
        listbox.file_data = []
    
    refresh_button.config(text="🔄 Refresh File List", state=tk.NORMAL)


def process_selected_file(listbox, ui_elements, status_label):
    """Process the selected file from the list"""
    selection = listbox.curselection()
    if not selection:
        messagebox.showwarning("No Selection", "Please select a file from the list.")
        return
    
    if not hasattr(listbox, 'file_data') or not listbox.file_data:
        messagebox.showerror("Error", "No file data available. Please refresh the list.")
        return
    
    selected_index = selection[0]
    if selected_index >= len(listbox.file_data):
        messagebox.showerror("Error", "Invalid selection. Please refresh the list.")
        return
    
    # Get form data
    notion_url = ui_elements['notion_entry'].get().strip()
    description = ui_elements['description_entry'].get().strip()
    
    if not notion_url or not description:
        messagebox.showerror("Error", "Please enter both Notion URL and description in the Calendar Events tab.")
        return
    
    webhook_url = os.getenv("WEBHOOK_URL", "").strip()
    if not webhook_url:
        messagebox.showerror("Error", "Webhook URL not set in .env file.")
        return
    
    # Get selected file info
    file_info = listbox.file_data[selected_index]
    local_file_path = file_info['filepath']
    
    if not os.path.exists(local_file_path):
        messagebox.showerror("Error", f"File not found: {local_file_path}")
        return
    
    # Update config with current UI values
    config["whisper_model"] = ui_elements['model_entry'].get().strip()
    config["whisper_device"] = ui_elements['device_entry'].get().strip()
    save_config()
    
    # Disable manual processing button during processing
    ui_elements['process_selected_button'].config(state=tk.DISABLED)
    
    def status_update(message):
        status_label.config(text=message)
    
    def processing_complete():
        ui_elements['process_selected_button'].config(state=tk.NORMAL)
    
    # Process the file in a separate thread
    def process_thread():
        try:
            status_update(f"🎬 Processing: {file_info['filename']}")
            
            # Process the file (extract audio then transcribe)
            transcription = process_audio_file(local_file_path, status_update)
            
            if transcription:
                # Send to webhook
                send_to_webhook(notion_url, description, transcription, file_info['url'], local_file_path)
                status_update("✅ File processed and sent to webhook!")
            else:
                status_update("❌ File processing failed")
                
        except Exception as e:
            logging.error(f"[Manual Process] Error processing selected file: {e}")
            status_update(f"❌ Error: {str(e)}")
        finally:
            processing_complete()
    
    # Start processing in background thread
    thread = threading.Thread(target=process_thread, daemon=True)
    thread.start()


def update_wait_timer(entry):
    try:
        minutes = int(entry.get().strip())
        if minutes > 0:
            config["wait_timer_minutes"] = minutes
            save_config()
    except ValueError:
        pass


def update_whisper_model(entry):
    config["whisper_model"] = entry.get().strip()
    save_config()


def update_whisper_device(entry):
    config["whisper_device"] = entry.get().strip()
    save_config()


if __name__ == "__main__":
    create_gui()