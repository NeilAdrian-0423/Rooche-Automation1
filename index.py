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
    "gladia_api_key": ""
}


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


def validate_gladia_api_key(api_key):
    """Validate Gladia API key format"""
    if not api_key:
        return False, "API key is empty"
    
    # Basic validation - Gladia API keys are usually long strings
    if len(api_key) < 10:
        return False, "API key seems too short"
    
    # Check for common whitespace issues
    if api_key != api_key.strip():
        return False, "API key contains leading/trailing whitespace"
    
    return True, "API key format looks valid"


def extract_audio(file_path, status_callback):
    """Extract audio from video/audio file and return path to extracted audio"""
    status_callback("🎧 Extracting audio from file...")
    logging.debug(f"[Audio] Starting audio extraction from: {file_path}")
    
    temp_audio_path = tempfile.mktemp(suffix=".mp3")
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-i", file_path, "-vn", "-acodec", "libmp3lame", "-q:a", "4", temp_audio_path],
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
        status_callback("❌ Audio extraction failed")
        return None
    except Exception as e:
        logging.error(f"[Audio] Unexpected error during audio extraction: {e}")
        status_callback("❌ Audio extraction failed")
        return None


def transcribe_with_gladia(audio_file_path, status_callback):
    """Transcribe audio file using Gladia API"""
    try:
        api_key = config.get("gladia_api_key", "").strip()
        if not api_key:
            status_callback("❌ Gladia API key not configured")
            return None

        # Validate API key
        is_valid, validation_msg = validate_gladia_api_key(api_key)
        if not is_valid:
            status_callback(f"❌ API key validation failed: {validation_msg}")
            return None

        status_callback("🎯 Starting Gladia transcription...")
        logging.debug(f"[Gladia] Starting transcription of: {audio_file_path}")
        logging.debug(f"[Gladia] API key length: {len(api_key)} characters")
        
        # Check if file exists and get file size
        if not os.path.exists(audio_file_path):
            status_callback("❌ Audio file not found")
            return None
            
        file_size = os.path.getsize(audio_file_path)
        logging.debug(f"[Gladia] Audio file size: {file_size} bytes")

        # Step 1: Upload audio to Gladia
        status_callback("📤 Uploading audio to Gladia...")
        upload_url = "https://api.gladia.io/v2/upload"
        headers = {
            "x-gladia-key": api_key
        }

        with open(audio_file_path, "rb") as f:
            files = {"audio": (os.path.basename(audio_file_path), f, "audio/mpeg")}
            try:
                upload_response = requests.post(upload_url, headers=headers, files=files, timeout=60)
                
                # Log the response details for debugging
                logging.debug(f"[Gladia] Upload response status: {upload_response.status_code}")
                logging.debug(f"[Gladia] Upload response headers: {upload_response.headers}")
                
                if upload_response.status_code != 200:
                    error_text = upload_response.text
                    logging.error(f"[Gladia] Upload failed with status {upload_response.status_code}: {error_text}")
                    status_callback(f"❌ Upload failed: {error_text}")
                    return None
                    
                upload_response.raise_for_status()
                
            except requests.exceptions.RequestException as e:
                logging.error(f"[Gladia] Upload request failed: {e}")
                status_callback(f"❌ Upload request failed: {e}")
                return None

        try:
            upload_data = upload_response.json()
            logging.debug(f"[Gladia] Upload response data: {upload_data}")
        except json.JSONDecodeError as e:
            logging.error(f"[Gladia] Failed to parse upload response: {e}")
            status_callback("❌ Invalid response from Gladia")
            return None
            
        if "audio_url" not in upload_data:
            logging.error(f"[Gladia] No audio_url in response: {upload_data}")
            status_callback("❌ Invalid upload response")
            return None
            
        audio_url = upload_data["audio_url"]
        logging.debug(f"[Gladia] Audio uploaded successfully: {audio_url}")

       # Step 2: Start transcription
        status_callback("🔄 Processing transcription...")
        transcription_url = "https://api.gladia.io/v2/transcription"

        transcription_payload = {
            "audio_url": audio_url,
        }

        try:
            transcription_response = requests.post(
                transcription_url,
                headers=headers,
                json=transcription_payload,
                timeout=30
            )
            
            logging.debug(f"[Gladia] Transcription response status: {transcription_response.status_code}")
            
            if transcription_response.status_code not in (200, 201):
                error_text = transcription_response.text
                logging.debug(f"[Gladia] Transcription started successfully: {transcription_data}")
                status_callback(f"❌ Transcription start failed: {error_text}")
                return None
                
            transcription_response.raise_for_status()
            
        except requests.exceptions.RequestException as e:
            logging.error(f"[Gladia] Transcription request failed: {e}")
            status_callback(f"❌ Transcription request failed: {e}")
            return None

        try:
            transcription_data = transcription_response.json()
            logging.debug(f"[Gladia] Transcription response data: {transcription_data}")
        except json.JSONDecodeError as e:
            logging.error(f"[Gladia] Failed to parse transcription response: {e}")
            status_callback("❌ Invalid transcription response")
            return None
            
        if "result_url" not in transcription_data:
            logging.error(f"[Gladia] No result_url in response: {transcription_data}")
            status_callback("❌ Invalid transcription response")
            return None
            
        result_url = transcription_data["result_url"]
        logging.debug(f"[Gladia] Transcription started, result URL: {result_url}")

        # Step 3: Poll for results
        status_callback("⏳ Waiting for transcription results...")
        for attempt in range(60):
            try:
                result_response = requests.get(result_url, headers=headers, timeout=30)
                
                if result_response.status_code != 200:
                    logging.error(f"[Gladia] Result polling failed: {result_response.text}")
                    status_callback("❌ Failed to check transcription status")
                    return None
                    
                result_response.raise_for_status()
                result_data = result_response.json()
                
            except requests.exceptions.RequestException as e:
                logging.error(f"[Gladia] Result polling request failed: {e}")
                status_callback(f"❌ Result polling failed: {e}")
                return None
            except json.JSONDecodeError as e:
                logging.error(f"[Gladia] Failed to parse result response: {e}")
                status_callback("❌ Invalid result response")
                return None
            
            status = result_data.get("status")
            logging.debug(f"[Gladia] Transcription status: {status}")

            if status == "done":
                transcription_text = ""
                transcription = result_data.get("result", {}).get("transcription", {})
                
                if "utterances" in transcription:
                    transcription_text = " ".join([u["text"] for u in transcription["utterances"]])
                elif "full_transcript" in transcription:
                    transcription_text = transcription["full_transcript"]
                else:
                    logging.warning(f"[Gladia] Unexpected transcription format: {transcription}")
                    transcription_text = str(transcription)

                status_callback("✅ Transcription completed!")
                logging.debug(f"[Gladia] Transcription completed successfully: {transcription_text[:100]}...")
                return transcription_text

            if status == "error":
                error_msg = result_data.get("error", "Unknown error")
                status_callback(f"❌ Transcription failed: {error_msg}")
                logging.error(f"[Gladia] Transcription error: {error_msg}")
                return None

            status_callback(f"⏳ Processing... ({status})")
            time.sleep(5)

        status_callback("❌ Transcription timed out")
        logging.error("[Gladia] Transcription timed out")
        return None

    except Exception as e:
        logging.error(f"[Gladia] Transcription failed: {e}")
        status_callback(f"❌ Gladia transcription failed: {e}")
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
        transcription = transcribe_with_gladia(audio_path, status_callback)
        
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
        status_callback(f"❌ Error processing file: {e}")
        return None


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


def handle_submission(notion_entry, description_entry, status_label):
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

    if not config.get("gladia_api_key"):
        messagebox.showerror("Error", "Gladia API key not set.")
        return

    submit_time = datetime.now(timezone.utc).astimezone()
    status_label.config(text="⏳ Waiting for audio/video file...")

    def on_transcription_complete(transcription, drive_url, local_file_path):
        send_to_webhook(notion_url, description, transcription, drive_url, local_file_path)
        status_label.config(text="✅ Transcription sent to webhook!")

    def status_update(message):
        status_label.config(text=message)

    threading.Thread(
        target=wait_for_audio_video_upload,
        args=(submit_time, on_transcription_complete, status_update),
        daemon=True
    ).start()


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


def update_gladia_api_key(entry):
    config["gladia_api_key"] = entry.get().strip()
    save_config()


def update_submit_button_state(submit_button):
    if config.get("history_path") and config.get("webhook_url") and config.get("gladia_api_key"):
        submit_button.config(state=tk.NORMAL)
    else:
        submit_button.config(state=tk.DISABLED)


def create_gui():
    load_config()

    root = tk.Tk()
    root.title("Notion + ShareX Monitor with Gladia Transcription")
    root.geometry("500x500")

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

    tk.Label(root, text="Gladia API Key:").pack()
    gladia_entry = tk.Entry(root, width=60, show="*")
    gladia_entry.insert(0, config.get("gladia_api_key", ""))
    gladia_entry.pack(pady=5)

    status_label = tk.Label(root, text="", fg="blue", wraplength=480)
    status_label.pack(pady=10)

    file_label = tk.Label(root, text="No file selected", fg="gray")
    file_label.pack()

    submit_button = tk.Button(
        root,
        text="Submit & Monitor",
        command=lambda: handle_submission(notion_entry, description_entry, status_label),
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

    webhook_entry.bind("<FocusOut>", lambda e: [update_webhook_url(webhook_entry), update_submit_button_state(submit_button)])
    gladia_entry.bind("<FocusOut>", lambda e: [update_gladia_api_key(gladia_entry), update_submit_button_state(submit_button)])

    info_label = tk.Label(
        root,
        text="This tool monitors ShareX history for new audio/video files,\ntranscribes them using Gladia API, and sends the transcription to your webhook.",
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