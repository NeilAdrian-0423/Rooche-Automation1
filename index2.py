import json
import time
import os
import threading
from datetime import datetime, timezone
import tkinter as tk
from tkinter import messagebox, filedialog
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
    "whisper_model": "base",  # Default to base model
    "whisper_device": "cpu",   # Default to CPU
    "wait_timer_minutes": 60   # Default to 60 minutes (1 hour)
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


def extract_audio(file_path, status_callback):
    """Extract audio from video/audio file and return path to extracted audio"""
    status_callback("🎧 Extracting audio from file...")
    logging.debug(f"[Audio] Starting audio extraction from: {file_path}")
    
    temp_audio_path = tempfile.mktemp(suffix=".wav")  # Using WAV for better compatibility with Whisper
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
        
        # Check if file exists
        if not os.path.exists(audio_file_path):
            status_callback("❌ Audio file not found")
            return None
            
        file_size = os.path.getsize(audio_file_path)
        logging.debug(f"[Whisper] Audio file size: {file_size} bytes")

        # Create a temporary directory for output
        output_dir = tempfile.mkdtemp()
        logging.debug(f"[Whisper] Using temporary directory: {output_dir}")

        try:
            # Use transcribe-anything package with correct API
            transcribe_anything(
                url_or_file=audio_file_path,
                output_dir=output_dir,
                task="transcribe",
                model=config.get("whisper_model", "base"),
                device=config.get("whisper_device", "cpu"),
                language=None  # Auto-detect language
            )
            
            # Find the output text file
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
        # Step 1: Extract audio from the file
        audio_path = extract_audio(file_path, status_callback)
        if not audio_path or not os.path.exists(audio_path):
            status_callback("❌ Failed to extract audio")
            return None

        # Step 2: Transcribe the extracted audio
        transcription = transcribe_locally(audio_path, status_callback)
        
        # Step 3: Clean up temporary audio file
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


def stop_monitoring(status_callback, ui_elements):
    """Stop the monitoring process and re-enable UI"""
    global monitoring_active
    monitoring_active = False
    status_callback("🛑 Monitoring stopped")
    logging.debug("[Monitor] Monitoring stopped by user or timer")
    
    # Re-enable UI elements
    enable_ui_elements(ui_elements, True)


def enable_ui_elements(ui_elements, enable=True):
    """Enable or disable UI elements"""
    state = tk.NORMAL if enable else tk.DISABLED
    
    # Enable/disable input fields and buttons
    ui_elements['notion_entry'].config(state=state)
    ui_elements['description_entry'].config(state=state)
    ui_elements['timer_entry'].config(state=state)
    ui_elements['model_entry'].config(state=state)
    ui_elements['device_entry'].config(state=state)
    ui_elements['submit_button'].config(state=state)
    ui_elements['select_button'].config(state=state)
    
    # Stop monitoring button has opposite state
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
        last_display_time = 0  # Track last display update to avoid skipping seconds
        
        while monitoring_active:
            current_time = time.time()
            elapsed_seconds = current_time - start_monitor_time
            
            # Check if timeout has been reached
            if elapsed_seconds >= timeout_seconds:
                monitoring_active = False
                status_callback("⏰ Time limit reached - monitoring stopped")
                enable_ui_elements(ui_elements, True)
                logging.debug("[Monitor] Timeout reached, stopping monitoring")
                return
            
            # Calculate remaining time
            remaining_seconds = int(timeout_seconds - elapsed_seconds)
            
            # Only update display if the second has changed to avoid skipping
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
                    if not monitoring_active:  # Check if monitoring was stopped
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
                                monitoring_active = False  # Stop monitoring once we find a file
                                status_callback("🎬 Found audio/video file!")
                                
                                local_file_path = entry["FilePath"]
                                if os.path.exists(local_file_path):
                                    # Process the file (extract audio then transcribe)
                                    transcription = process_audio_file(local_file_path, status_callback)
                                    if transcription:
                                        drive_url = entry.get("URL", "")
                                        callback(transcription, drive_url, local_file_path)
                                        # Re-enable UI after successful completion
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
                                # Found a file but it's not audio/video - ignore it and continue monitoring
                                logging.debug(f"[Monitor] Ignoring non-audio/video file: {file_name}")
                                continue

            except Exception as e:
                logging.error(f"[Monitor] Error reading history: {e}")
                status_callback(f"⚠️ Error reading history: {str(e)}")

            time.sleep(1)  # Check every 1 second for smoother timer display
        
        # If we exit the loop without finding a file, it means monitoring was stopped
        if not monitoring_active:
            enable_ui_elements(ui_elements, True)
    
    # Start monitoring in a separate thread
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

    # Get the current timer value from the UI field, not from config
    try:
        wait_minutes = int(ui_elements['timer_entry'].get().strip())
        if wait_minutes <= 0:
            messagebox.showerror("Error", "Time limit must be greater than 0 minutes.")
            return
        # Update config with the current value
        config["wait_timer_minutes"] = wait_minutes
        save_config()
    except ValueError:
        messagebox.showerror("Error", "Please enter a valid number for time limit.")
        return

    submit_time = datetime.now(timezone.utc).astimezone()
    
    # Also update other config values from UI fields
    config["whisper_model"] = ui_elements['model_entry'].get().strip()
    config["whisper_device"] = ui_elements['device_entry'].get().strip()
    save_config()
    
    # Disable UI elements when monitoring starts
    enable_ui_elements(ui_elements, False)
    
    def on_transcription_complete(transcription, drive_url, local_file_path):
        send_to_webhook(notion_url, description, transcription, drive_url, local_file_path)
        status_label.config(text="✅ Transcription sent to webhook!")

    def status_update(message):
        status_label.config(text=message)

    status_update(f"🚀 Starting monitoring with {wait_minutes} minute time limit...")
    
    # Start monitoring with timeout
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


def update_webhook_url(entry):
    config["webhook_url"] = entry.get().strip()
    save_config()


def update_whisper_model(entry):
    config["whisper_model"] = entry.get().strip()
    save_config()


def update_whisper_device(entry):
    config["whisper_device"] = entry.get().strip()
    save_config()


def update_wait_timer(entry):
    try:
        minutes = int(entry.get().strip())
        if minutes > 0:
            config["wait_timer_minutes"] = minutes
            save_config()
    except ValueError:
        pass  # Ignore invalid input


def update_submit_button_state(submit_button):
    if config.get("history_path") and os.getenv("WEBHOOK_URL", "").strip():
        submit_button.config(state=tk.NORMAL)
    else:
        submit_button.config(state=tk.DISABLED)


def create_gui():
    load_config()

    root = tk.Tk()
    root.title("Notion + ShareX Monitor with Local Transcription")
    root.geometry("500x650")

    tk.Label(root, text="Notion URL:").pack(pady=(10, 0))
    notion_entry = tk.Entry(root, width=60)
    notion_entry.pack(pady=5)

    tk.Label(root, text="Description:").pack()
    description_entry = tk.Entry(root, width=60)
    description_entry.pack(pady=5)

    # Wait timer configuration
    tk.Label(root, text="Time Limit (minutes):").pack()
    timer_entry = tk.Entry(root, width=60)
    timer_entry.insert(0, str(config.get("wait_timer_minutes", 60)))
    timer_entry.pack(pady=5)

    # Whisper model selection
    tk.Label(root, text="Whisper Model (tiny,base,small,medium,large):").pack()
    model_entry = tk.Entry(root, width=60)
    model_entry.insert(0, config.get("whisper_model", "base"))
    model_entry.pack(pady=5)

    # Device selection
    tk.Label(root, text="Device (cpu,cuda):").pack()
    device_entry = tk.Entry(root, width=60)
    device_entry.insert(0, config.get("whisper_device", "cpu"))
    device_entry.pack(pady=5)

    status_label = tk.Label(root, text="", fg="blue", wraplength=480)
    status_label.pack(pady=10)

    file_label = tk.Label(root, text="No file selected", fg="gray")
    file_label.pack()

    # Create UI elements dictionary for easier management
    ui_elements = {}

    # Stop monitoring button
    reset_button = tk.Button(
        root,
        text="Stop Monitoring",
        state=tk.DISABLED,
        bg="#FF5722",
        fg="white",
        font=("Arial", 9)
    )
    reset_button.pack(pady=5)

    submit_button = tk.Button(
        root,
        text="Start Monitoring",
        state=tk.DISABLED,
        bg="#4CAF50",
        fg="white",
        font=("Arial", 10, "bold")
    )
    submit_button.pack(pady=10)

    select_button = tk.Button(
        root,
        text="Select ShareX history.json",
        command=lambda: select_history_file(file_label, submit_button)
    )
    select_button.pack(pady=5)

    # Populate UI elements dictionary
    ui_elements = {
        'notion_entry': notion_entry,
        'description_entry': description_entry,
        'timer_entry': timer_entry,
        'model_entry': model_entry,
        'device_entry': device_entry,
        'submit_button': submit_button,
        'select_button': select_button,
        'reset_button': reset_button
    }

    # Configure button commands with ui_elements
    reset_button.config(
        command=lambda: stop_monitoring(lambda msg: status_label.config(text=msg), ui_elements)
    )
    submit_button.config(
        command=lambda: handle_submission(ui_elements, status_label)
    )

    # Bindings for updates
    timer_entry.bind("<FocusOut>", lambda e: update_wait_timer(timer_entry))
    timer_entry.bind("<KeyRelease>", lambda e: update_wait_timer(timer_entry))  # Update on key release too
    model_entry.bind("<FocusOut>", lambda e: update_whisper_model(model_entry))
    device_entry.bind("<FocusOut>", lambda e: update_whisper_device(device_entry))

    info_label = tk.Label(
        root,
        text="This tool monitors ShareX history for new audio/video files\n"
             "for a specified time limit. Once the time limit is reached,\n"
             "monitoring stops automatically. When an audio/video file is found,\n"
             "it transcribes it locally using Whisper and sends to your webhook.\n\n"
             "Note: First run will download the Whisper model (base is ~150MB).",
        fg="gray",
        font=("Arial", 8),
        wraplength=480
    )
    info_label.pack(pady=10)

    if config.get("history_path") and os.path.exists(config["history_path"]):
        file_label.config(text=f"Selected: {os.path.basename(config['history_path'])}")

    update_submit_button_state(submit_button)

    root.mainloop()


if __name__ == "__main__":
    create_gui()