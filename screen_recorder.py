import cv2
import numpy as np
import mss
import tkinter as tk
from tkinter import ttk, messagebox
import threading
from datetime import datetime
import os
import pickle
import pyautogui
import queue
import wave
import subprocess
import tempfile

# Audio imports
try:
    import pyaudio
    import sounddevice as sd
    import soundfile as sf
    AUDIO_AVAILABLE = True
except ImportError:
    AUDIO_AVAILABLE = False
    print("Audio recording not available. Install with: pip install pyaudio sounddevice soundfile")

# Google Drive imports (optional)
try:
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    GOOGLE_DRIVE_AVAILABLE = True
except ImportError:
    GOOGLE_DRIVE_AVAILABLE = False
    print("Google Drive API not installed. Upload feature disabled.")

class AudioRecorder:
    def __init__(self):
        self.recording = False
        self.audio_queue = queue.Queue()
        self.sample_rate = 44100
        self.channels = 2
        self.chunk = 1024
        self.audio_thread = None
        self.mic_device = None
        self.speaker_device = None
        
    def get_audio_devices(self):
        """Get list of available audio devices"""
        if not AUDIO_AVAILABLE:
            return [], []
            
        devices = sd.query_devices()
        mic_devices = []
        speaker_devices = []
        
        for i, device in enumerate(devices):
            if device['max_input_channels'] > 0:
                mic_devices.append((i, device['name']))
            if device['max_output_channels'] > 0:
                speaker_devices.append((i, device['name']))
                
        return mic_devices, speaker_devices
    
    def start_recording(self, mic_device_id=None, record_speaker=False, record_mic=True):
        """Start audio recording"""
        if not AUDIO_AVAILABLE:
            return None
            
        self.recording = True
        self.audio_filename = f"audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        
        def record_audio():
            p = pyaudio.PyAudio()
            
            # Setup microphone stream
            mic_stream = None
            if record_mic and mic_device_id is not None:
                try:
                    mic_stream = p.open(
                        format=pyaudio.paInt16,
                        channels=self.channels,
                        rate=self.sample_rate,
                        input=True,
                        input_device_index=mic_device_id,
                        frames_per_buffer=self.chunk
                    )
                except Exception as e:
                    print(f"Mic recording error: {e}")
            
            # Setup speaker recording (using stereo mix/loopback)
            speaker_stream = None
            if record_speaker:
                try:
                    # Try to find stereo mix or loopback device
                    for i in range(p.get_device_count()):
                        info = p.get_device_info_by_index(i)
                        if 'stereo mix' in info['name'].lower() or 'loopback' in info['name'].lower():
                            speaker_stream = p.open(
                                format=pyaudio.paInt16,
                                channels=self.channels,
                                rate=self.sample_rate,
                                input=True,
                                input_device_index=i,
                                frames_per_buffer=self.chunk
                            )
                            break
                except Exception as e:
                    print(f"Speaker recording error: {e}")
            
            # Record audio
            frames = []
            while self.recording:
                try:
                    mixed_data = None
                    
                    if mic_stream:
                        mic_data = mic_stream.read(self.chunk, exception_on_overflow=False)
                        mic_array = np.frombuffer(mic_data, dtype=np.int16)
                        if mixed_data is None:
                            mixed_data = mic_array
                        else:
                            mixed_data = mixed_data + mic_array
                    
                    if speaker_stream:
                        speaker_data = speaker_stream.read(self.chunk, exception_on_overflow=False)
                        speaker_array = np.frombuffer(speaker_data, dtype=np.int16)
                        if mixed_data is None:
                            mixed_data = speaker_array
                        else:
                            mixed_data = mixed_data + speaker_array
                    
                    if mixed_data is not None:
                        # Normalize to prevent clipping
                        mixed_data = np.clip(mixed_data, -32768, 32767)
                        frames.append(mixed_data.astype(np.int16).tobytes())
                        
                except Exception as e:
                    continue
            
            # Close streams
            if mic_stream:
                mic_stream.stop_stream()
                mic_stream.close()
            if speaker_stream:
                speaker_stream.stop_stream()
                speaker_stream.close()
            p.terminate()
            
            # Save audio file
            if frames:
                wf = wave.open(self.audio_filename, 'wb')
                wf.setnchannels(self.channels)
                wf.setsampwidth(p.get_sample_size(pyaudio.paInt16))
                wf.setframerate(self.sample_rate)
                wf.writeframes(b''.join(frames))
                wf.close()
                return self.audio_filename
            return None
        
        self.audio_thread = threading.Thread(target=record_audio)
        self.audio_thread.daemon = True
        self.audio_thread.start()
        
    def stop_recording(self):
        """Stop audio recording"""
        self.recording = False
        if self.audio_thread:
            self.audio_thread.join(timeout=2)
        return self.audio_filename

class ScreenRecorder:
    def __init__(self):
        self.recording = False
        self.output_file = None
        self.audio_recorder = AudioRecorder()
        
    def start_recording(self, region=None, mic_device=None, record_speaker=False, record_mic=True):
        """Start recording screen with audio"""
        self.recording = True
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        video_file = f"video_temp_{timestamp}.mp4"
        self.output_file = f"recording_{timestamp}.mp4"
        
        # Start audio recording
        audio_file = None
        if AUDIO_AVAILABLE and (record_mic or record_speaker):
            self.audio_recorder.start_recording(mic_device, record_speaker, record_mic)
        
        # Get screen dimensions
        if region:
            x, y, width, height = region
        else:
            width, height = pyautogui.size()
            x, y = 0, 0
            
        # Video writer setup
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        fps = 20.0
        out = cv2.VideoWriter(video_file, fourcc, fps, (width, height))
        
        with mss.mss() as sct:
            monitor = {"top": y, "left": x, "width": width, "height": height}
            
            while self.recording:
                img = sct.grab(monitor)
                frame = np.array(img)
                frame = cv2.cvtColor(frame, cv2.COLOR_BGRA2BGR)
                out.write(frame)
                
        out.release()
        cv2.destroyAllWindows()
        
        # Stop audio recording
        if AUDIO_AVAILABLE and (record_mic or record_speaker):
            audio_file = self.audio_recorder.stop_recording()
        
        # Merge audio and video using ffmpeg if audio was recorded
        if audio_file and os.path.exists(audio_file):
            self.merge_audio_video(video_file, audio_file, self.output_file)
            # Clean up temp files
            try:
                os.remove(video_file)
                os.remove(audio_file)
            except:
                pass
        else:
            os.rename(video_file, self.output_file)
            
        return self.output_file
        
    def merge_audio_video(self, video_file, audio_file, output_file):
        """Merge audio and video files using ffmpeg"""
        try:
            # Check if ffmpeg is available
            subprocess.run(['ffmpeg', '-version'], capture_output=True, check=True)
            
            cmd = [
                'ffmpeg',
                '-i', video_file,
                '-i', audio_file,
                '-c:v', 'copy',
                '-c:a', 'aac',
                '-strict', 'experimental',
                output_file,
                '-y'
            ]
            subprocess.run(cmd, capture_output=True, check=True)
            print("Audio and video merged successfully")
        except subprocess.CalledProcessError:
            print("ffmpeg not found or merge failed. Saving video without audio.")
            os.rename(video_file, output_file)
        except FileNotFoundError:
            print("ffmpeg not installed. Install it for audio support.")
            print("Download from: https://ffmpeg.org/download.html")
            os.rename(video_file, output_file)
        
    def stop_recording(self):
        self.recording = False
        self.audio_recorder.stop_recording()

class RegionSelector:
    def __init__(self):
        self.start_x = None
        self.start_y = None
        self.rect = None
        self.region = None
        
    def select_region(self):
        """Create transparent overlay for region selection"""
        root = tk.Toplevel()
        root.attributes('-fullscreen', True)
        root.attributes('-alpha', 0.3)
        root.attributes('-topmost', True)
        root.configure(background='grey')
        
        canvas = tk.Canvas(root, highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        
        label = tk.Label(root, text="Click and drag to select region (ESC to cancel)", 
                        font=("Arial", 16), bg="grey", fg="white")
        label.place(relx=0.5, rely=0.05, anchor="center")
        
        def on_mouse_down(event):
            self.start_x = event.x
            self.start_y = event.y
            if self.rect:
                canvas.delete(self.rect)
            self.rect = canvas.create_rectangle(
                self.start_x, self.start_y, self.start_x, self.start_y,
                outline='red', width=2, fill='red', stipple='gray50'
            )
            
        def on_mouse_drag(event):
            canvas.coords(self.rect, self.start_x, self.start_y, event.x, event.y)
            
        def on_mouse_up(event):
            end_x, end_y = event.x, event.y
            self.region = (
                min(self.start_x, end_x),
                min(self.start_y, end_y),
                abs(end_x - self.start_x),
                abs(end_y - self.start_y)
            )
            root.destroy()
            
        def on_escape(event):
            self.region = None
            root.destroy()
            
        canvas.bind("<Button-1>", on_mouse_down)
        canvas.bind("<B1-Motion>", on_mouse_drag)
        canvas.bind("<ButtonRelease-1>", on_mouse_up)
        root.bind("<Escape>", on_escape)
        
        root.wait_window()
        return self.region

class GoogleDriveUploader:
    SCOPES = ['https://www.googleapis.com/auth/drive.file']
    
    def __init__(self):
        self.service = None
        if GOOGLE_DRIVE_AVAILABLE:
            try:
                self.service = self.authenticate()
            except Exception as e:
                print(f"Google Drive authentication failed: {e}")
        
    def authenticate(self):
        """Authenticate with Google Drive API"""
        creds = None
        
        if os.path.exists('token.pickle'):
            with open('token.pickle', 'rb') as token:
                creds = pickle.load(token)
                
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not os.path.exists('credentials.json'):
                    print("credentials.json not found. Google Drive upload disabled.")
                    return None
                flow = InstalledAppFlow.from_client_secrets_file(
                    'credentials.json', self.SCOPES)
                creds = flow.run_local_server(port=0)
                
            with open('token.pickle', 'wb') as token:
                pickle.dump(creds, token)
                
        return build('drive', 'v3', credentials=creds)
        
    def upload_file(self, filepath):
        """Upload file to Google Drive"""
        if not self.service:
            print("Google Drive service not available")
            return None
            
        file_metadata = {
            'name': os.path.basename(filepath),
            'mimeType': 'video/mp4'
        }
        
        media = MediaFileUpload(filepath, mimetype='video/mp4', resumable=True)
        
        try:
            file = self.service.files().create(
                body=file_metadata,
                media_body=media,
                fields='id, webViewLink'
            ).execute()
            
            self.service.permissions().create(
                fileId=file.get('id'),
                body={'type': 'anyone', 'role': 'reader'}
            ).execute()
            
            return file.get('webViewLink')
            
        except Exception as e:
            print(f"Upload error: {e}")
            return None

class ScreenRecorderApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Screen Recorder with Audio - ShareX Clone")
        self.root.geometry("450x500")
        
        self.recorder = ScreenRecorder()
        self.selector = RegionSelector()
        self.uploader = GoogleDriveUploader()
        self.selected_region = None
        self.recording_thread = None
        
        self.setup_ui()
        self.populate_audio_devices()
        
    def setup_ui(self):
        # Title
        title = tk.Label(self.root, text="Screen Recorder with Audio", font=("Arial", 16, "bold"))
        title.pack(pady=10)
        
        # Audio Settings Frame
        audio_frame = tk.LabelFrame(self.root, text="Audio Settings", font=("Arial", 10, "bold"))
        audio_frame.pack(pady=10, padx=20, fill="x")
        
        # Microphone selection
        mic_frame = tk.Frame(audio_frame)
        mic_frame.pack(fill="x", padx=10, pady=5)
        
        self.record_mic_var = tk.BooleanVar(value=True)
        self.mic_checkbox = tk.Checkbutton(
            mic_frame, 
            text="Record Microphone:",
            variable=self.record_mic_var,
            command=self.toggle_mic,
            state="normal" if AUDIO_AVAILABLE else "disabled"
        )
        self.mic_checkbox.pack(side="left")
        
        self.mic_combo = ttk.Combobox(mic_frame, width=30, state="readonly" if AUDIO_AVAILABLE else "disabled")
        self.mic_combo.pack(side="left", padx=5)
        
        # Speaker/System audio selection
        speaker_frame = tk.Frame(audio_frame)
        speaker_frame.pack(fill="x", padx=10, pady=5)
        
        self.record_speaker_var = tk.BooleanVar(value=False)
        self.speaker_checkbox = tk.Checkbutton(
            speaker_frame, 
            text="Record System Audio:",
            variable=self.record_speaker_var,
            state="normal" if AUDIO_AVAILABLE else "disabled"
        )
        self.speaker_checkbox.pack(side="left")
        
        speaker_info = tk.Label(
            speaker_frame, 
            text="(Requires Stereo Mix enabled)",
            font=("Arial", 8),
            fg="gray"
        )
        speaker_info.pack(side="left", padx=5)
        
        # Recording Settings Frame
        record_frame = tk.LabelFrame(self.root, text="Recording Settings", font=("Arial", 10, "bold"))
        record_frame.pack(pady=10, padx=20, fill="x")
        
        # Region selection button
        self.select_btn = tk.Button(
            record_frame, text="📐 Select Region", 
            command=self.select_region,
            font=("Arial", 11),
            width=18,
            height=2
        )
        self.select_btn.pack(pady=5)
        
        # Region info label
        self.region_label = tk.Label(
            record_frame, 
            text="Recording: Full Screen",
            font=("Arial", 9),
            fg="gray"
        )
        self.region_label.pack()
        
        # Record button
        self.record_btn = tk.Button(
            self.root, text="🔴 Start Recording", 
            command=self.toggle_recording,
            font=("Arial", 12),
            width=20,
            height=2,
            bg="#ff4444",
            fg="white"
        )
        self.record_btn.pack(pady=10)
        
        # Upload Settings Frame
        upload_frame = tk.LabelFrame(self.root, text="Upload Settings", font=("Arial", 10, "bold"))
        upload_frame.pack(pady=10, padx=20, fill="x")
        
        # Auto upload checkbox
        self.auto_upload_var = tk.BooleanVar(value=False)
        self.auto_upload_cb = tk.Checkbutton(
            upload_frame, 
            text="Auto-upload to Google Drive",
            variable=self.auto_upload_var,
            font=("Arial", 10),
            state="normal" if GOOGLE_DRIVE_AVAILABLE else "disabled"
        )
        self.auto_upload_cb.pack(pady=5)
        
        # Status label
        self.status_label = tk.Label(
            self.root, 
            text="Ready to record",
            font=("Arial", 10),
            fg="green"
        )
        self.status_label.pack(pady=10)
        
        # Instructions
        instructions = tk.Label(
            self.root,
            text="Note: For system audio, enable 'Stereo Mix' in Windows Sound Settings\n" +
                 "FFmpeg required for audio+video merge (download from ffmpeg.org)",
            font=("Arial", 8),
            fg="gray",
            justify="center"
        )
        instructions.pack(pady=5)
        
    def populate_audio_devices(self):
        """Populate audio device dropdowns"""
        if not AUDIO_AVAILABLE:
            self.mic_combo['values'] = ["Audio libraries not installed"]
            return
            
        audio_rec = AudioRecorder()
        mic_devices, speaker_devices = audio_rec.get_audio_devices()
        
        if mic_devices:
            device_names = [name for _, name in mic_devices]
            self.mic_combo['values'] = device_names
            self.mic_combo.current(0)
            self.mic_devices = mic_devices
        else:
            self.mic_combo['values'] = ["No microphone found"]
            
    def toggle_mic(self):
        """Enable/disable mic dropdown based on checkbox"""
        if self.record_mic_var.get():
            self.mic_combo['state'] = "readonly"
        else:
            self.mic_combo['state'] = "disabled"
            
    def select_region(self):
        self.root.withdraw()
        self.selected_region = self.selector.select_region()
        self.root.deiconify()
        
        if self.selected_region:
            x, y, w, h = self.selected_region
            self.region_label.config(text=f"Recording: Region ({w}x{h})")
            self.status_label.config(text="Region selected", fg="blue")
        else:
            self.region_label.config(text="Recording: Full Screen")
            
    def toggle_recording(self):
        if not self.recorder.recording:
            self.start_recording()
        else:
            self.stop_recording()
            
    def start_recording(self):
        self.record_btn.config(text="⬜ Stop Recording", bg="#888888")
        self.status_label.config(text="Recording...", fg="red")
        self.select_btn.config(state="disabled")
        self.mic_checkbox.config(state="disabled")
        self.speaker_checkbox.config(state="disabled")
        self.mic_combo.config(state="disabled")
        
        # Get selected microphone device
        mic_device_id = None
        if AUDIO_AVAILABLE and self.record_mic_var.get() and hasattr(self, 'mic_devices'):
            selected_index = self.mic_combo.current()
            if selected_index >= 0:
                mic_device_id = self.mic_devices[selected_index][0]
        
        def record():
            filename = self.recorder.start_recording(
                self.selected_region,
                mic_device=mic_device_id,
                record_speaker=self.record_speaker_var.get(),
                record_mic=self.record_mic_var.get()
            )
            self.root.after(0, self.on_recording_finished, filename)
            
        self.recording_thread = threading.Thread(target=record)
        self.recording_thread.daemon = True
        self.recording_thread.start()
        
    def stop_recording(self):
        self.recorder.stop_recording()
        self.status_label.config(text="Stopping...", fg="orange")
        
    def on_recording_finished(self, filename):
        self.record_btn.config(text="🔴 Start Recording", bg="#ff4444")
        self.select_btn.config(state="normal")
        self.mic_checkbox.config(state="normal")
        self.speaker_checkbox.config(state="normal")
        self.mic_combo.config(state="readonly" if self.record_mic_var.get() else "disabled")
        
        if filename and os.path.exists(filename):
            file_size = os.path.getsize(filename) / (1024 * 1024)
            self.status_label.config(
                text=f"Saved: {filename} ({file_size:.1f} MB)", 
                fg="green"
            )
            
            if self.auto_upload_var.get() and GOOGLE_DRIVE_AVAILABLE:
                self.status_label.config(text="Uploading to Google Drive...", fg="blue")
                
                def upload():
                    link = self.uploader.upload_file(filename)
                    if link:
                        self.root.after(0, self.show_upload_success, link)
                    else:
                        self.root.after(0, self.show_upload_error)
                        
                upload_thread = threading.Thread(target=upload)
                upload_thread.daemon = True
                upload_thread.start()
        else:
            self.status_label.config(text="Recording failed", fg="red")
            
    def show_upload_success(self, link):
        self.status_label.config(text="Upload successful!", fg="green")
        
        popup = tk.Toplevel(self.root)
        popup.title("Upload Complete")
        popup.geometry("400x150")
        
        tk.Label(popup, text="File uploaded successfully!", font=("Arial", 12)).pack(pady=10)
        
        link_text = tk.Text(popup, height=2, width=50)
        link_text.pack(pady=5)
        link_text.insert("1.0", link)
        link_text.config(state="disabled")
        
        tk.Button(popup, text="Copy Link", 
                 command=lambda: self.root.clipboard_append(link)).pack(pady=5)
        tk.Button(popup, text="OK", command=popup.destroy).pack()
        
    def show_upload_error(self):
        self.status_label.config(text="Upload failed", fg="red")

def main():
    # Check dependencies
    print("ShareX Clone - Screen Recorder with Audio")
    print("-" * 40)
    
    required_modules = ['cv2', 'mss', 'numpy', 'pyautogui']
    missing_modules = []
    
    for module in required_modules:
        try:
            __import__(module)
        except ImportError:
            missing_modules.append(module)
            
    if missing_modules:
        print("❌ Missing required modules:")
        print(f"   Please install: pip install {' '.join(missing_modules)}")
        print("\n📦 Full installation command:")
        print("   pip install opencv-python mss numpy pyautogui")
        
    if not AUDIO_AVAILABLE:
        print("\n🔊 Audio recording not available. For audio support, install:")
        print("   pip install pyaudio sounddevice soundfile")
        print("\n   Note: On Windows, you might need to install pyaudio wheel:")
        print("   pip install pipwin")
        print("   pipwin install pyaudio")
        
    if not GOOGLE_DRIVE_AVAILABLE:
        print("\n☁️ For Google Drive support, install:")
        print("   pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib")
    
    print("\n📹 For audio+video merging, install FFmpeg:")
    print("   Download from: https://ffmpeg.org/download.html")
    print("   Add to system PATH after installation")
    
    print("\n" + "="*40)
    print("Starting application...")
    print("="*40 + "\n")
    
    if missing_modules:
        print("Cannot start: Missing core dependencies")
        return
        
    root = tk.Tk()
    app = ScreenRecorderApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()