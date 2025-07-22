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
    "webhook_url": "",
    "whisper_model": "base",  # Default to base model
    "whisper_device": "cpu",   # Default to CPU
    "wait_timer_minutes": 60   # Default to 60 minutes (1 hour)
}

# Global variables for timer control
timer_active = False
timer_thread = None
timer_start_time = None
timer_end_callback = None


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


def start_wait_timer(duration_minutes, status_callback, end_callback):
    """Start the wait timer"""
    global timer_active, timer_thread, timer_start_time, timer_end_callback
    
    timer_active = True
    timer_start_time = datetime.now()
    timer_end_callback = end_callback
    
    def timer_worker():
        global timer_active
        total_seconds = duration_minutes * 60
        
        for remaining_seconds in range(total_seconds, 0, -1):
            if not timer_active:
                return
            
            hours = remaining_seconds // 3600
            minutes = (remaining_seconds % 3600) // 60
            seconds = remaining_seconds % 60
            
            if hours > 0:
                time_str = f"{hours:02d}:{minutes:02d}:{seconds:02d}"
            else:
                time_str = f"{minutes:02d}:{seconds:02d}"
            
            status_callback(f"⏰ Waiting... {time_str} remaining")
            time.sleep(1)
        
        if timer_active:
            timer_active = False
            status_callback("⏰ Timer finished!")
            if timer_end_callback:
                timer_end_callback()
    
    timer_thread = threading.Thread(target=timer_worker, daemon=True)
    timer_thread.start()


def reset_timer(status_callback):
    """Reset the wait timer"""
    global timer_active
    timer_active = False
    status_callback("🔄 Timer reset")
    logging.debug("[Timer] Timer reset by user")


def wait_for_audio_video_upload(after_dt: datetime, callback, status_callback):
    logging.debug(f"[Monitor] Watching for uploads after {after_dt.isoformat()}")

    while True:
        try:
            with open(config["history_path"], 'r', encoding='utf-8') as f:
                content = f.read()

            raw_entries = "[" + content.replace("}\n{", "},\n{") + "]"
            history = json.loads(raw_entries)

            for entry in reversed(history):
                if "FilePath" in entry and "DateTime" in entry:
                    entry_time = datetime.fromisoformat(entry["DateTime"].replace("Z", "+00:00"))
                    if entry_time.tzinfo is None:
                        entry_time = entry_time.replace(tzinfo=timezone.utc)
                    if entry_time > after_dt:
                        logging.debug(f"[Monitor] New file found: {entry['FileName']}")
                        file_name = entry.get("FileName", "").lower()
                        valid_ext = ['.mp3', '.mp4', '.wav', '.m4a', '.flac', '.ogg', '.webm', '.avi', '.mov', '.wmv']
                        if any(file_name.endswith(ext) for ext in valid_ext):
                            status_callback("🎬 Found audio/video file!")
                            local_file_path = entry["FilePath"]
                            if os.path.exists(local_file_path):
                                # Process the file (extract audio then transcribe)
                                transcription = process_audio_file(local_file_path, status_callback)
                                if transcription:
                                    drive_url = entry.get("URL", "")
                                    callback(transcription, drive_url, local_file_path)
                                    return
                                else:
                                    status_callback("❌ File processing failed")
                                    return
                            else:
                                status_callback(f"❌ File not found: {local_file_path}")
                                return
                        else:
                            status_callback("⚠️ File is not an audio/video file")
                            return

        except Exception as e:
            logging.error(f"[Monitor] Error reading history: {e}")
            status_callback(f"⚠️ Error reading history: {str(e)}")

        time.sleep(2)


def send_to_webhook(notion_url, description, transcription, drive_url, local_file_path):
    webhook_url = config.get("webhook_url", "").strip()
    if not webhook_url:
        logging.warning("[Webhook] No webhook URL configured.")
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


def handle_submission(notion_entry, description_entry, status_label, reset_button):
    notion_url = notion_entry.get().strip()
    description = description_entry.get().strip()

    if not notion_url or not description:
        messagebox.showerror("Error", "Please enter both Notion URL and description.")
        return

    if not config.get("history_path"):
        messagebox.showerror("Error", "No ShareX history.json selected.")
        return

    if not config.get("webhook_url"):
        messagebox.showerror("Error", "Webhook URL not set.")
        return

    submit_time = datetime.now(timezone.utc).astimezone()
    
    def on_transcription_complete(transcription, drive_url, local_file_path):
        # Reset timer when transcription is complete
        reset_timer(lambda msg: None)
        send_to_webhook(notion_url, description, transcription, drive_url, local_file_path)
        status_label.config(text="✅ Transcription sent to webhook!")
        reset_button.config(state=tk.DISABLED)

    def status_update(message):
        status_label.config(text=message)
        # Enable reset button when timer is running
        if "⏰ Waiting..." in message:
            reset_button.config(state=tk.NORMAL)
        elif "Timer reset" in message or "Timer finished" in message:
            reset_button.config(state=tk.DISABLED)

    def on_timer_end():
        status_update("⏳ Timer finished, monitoring for audio/video file...")
        reset_button.config(state=tk.DISABLED)
        threading.Thread(
            target=wait_for_audio_video_upload,
            args=(submit_time, on_transcription_complete, status_update),
            daemon=True
        ).start()

    # Start the wait timer first
    wait_minutes = config.get("wait_timer_minutes", 60)
    status_update(f"⏰ Starting {wait_minutes} minute wait timer...")
    start_wait_timer(wait_minutes, status_update, on_timer_end)


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
    if config.get("history_path") and config.get("webhook_url"):
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

    tk.Label(root, text="Webhook URL:").pack()
    webhook_entry = tk.Entry(root, width=60)
    webhook_entry.insert(0, config.get("webhook_url", ""))
    webhook_entry.pack(pady=5)

    # Wait timer configuration
    tk.Label(root, text="Wait Timer (minutes):").pack()
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

    # Reset timer button
    reset_button = tk.Button(
        root,
        text="Reset Timer",
        command=lambda: reset_timer(lambda msg: status_label.config(text=msg)),
        state=tk.DISABLED,
        bg="#FF5722",
        fg="white",
        font=("Arial", 9)
    )
    reset_button.pack(pady=5)

    submit_button = tk.Button(
        root,
        text="Submit & Start Timer",
        command=lambda: handle_submission(notion_entry, description_entry, status_label, reset_button),
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

    # Bindings for updates
    webhook_entry.bind("<FocusOut>", lambda e: [update_webhook_url(webhook_entry), update_submit_button_state(submit_button)])
    timer_entry.bind("<FocusOut>", lambda e: update_wait_timer(timer_entry))
    model_entry.bind("<FocusOut>", lambda e: update_whisper_model(model_entry))
    device_entry.bind("<FocusOut>", lambda e: update_whisper_device(device_entry))

    info_label = tk.Label(
        root,
        text="This tool waits for the specified time, then monitors ShareX history for\n"
             "new audio/video files, transcribes them locally using Whisper,\n"
             "and sends the transcription to your webhook.\n\n"
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