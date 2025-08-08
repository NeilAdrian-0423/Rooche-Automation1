"""Audio processing and transcription service."""

import os
import tempfile
import subprocess
import logging
from typing import Optional
from transcribe_anything import transcribe_anything

class AudioProcessor:
    def __init__(self, config_manager):
        self.config = config_manager
    
    def extract_audio(self, file_path: str, status_callback) -> Optional[str]:
        """Extract audio from video/audio file and return path to extracted audio."""
        status_callback("🎧 Extracting audio from file...")
        logging.debug(f"[Audio] Starting audio extraction from: {file_path}")
        
        temp_audio_path = tempfile.mktemp(suffix=".wav")
        try:
            subprocess.run(
                ["ffmpeg", "-y", "-i", file_path, "-vn", "-acodec", "pcm_s16le", 
                 "-ar", "16000", "-ac", "1", temp_audio_path],
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
    
    def transcribe_locally(self, audio_file_path: str, status_callback) -> Optional[str]:
        """Transcribe audio file using local Whisper model."""
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
                    model=self.config.get("whisper_model", "base"),
                    device=self.config.get("whisper_device", "cpu"),
                    language=None
                )
                
                base_name = "out"
                output_txt = os.path.join(output_dir, f"{base_name}.txt")
                
                if os.path.exists(output_txt):
                    with open(output_txt, "r", encoding="utf-8") as f:
                        transcription_text = f.read()
                    
                    status_callback("✅ Transcription completed!")
                    logging.debug(f"[Whisper] Transcription completed successfully")
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
    
    def process_file(self, file_path: str, status_callback) -> Optional[str]:
        """Process audio/video file: extract audio first, then transcribe."""
        try:
            audio_path = self.extract_audio(file_path, status_callback)
            if not audio_path or not os.path.exists(audio_path):
                status_callback("❌ Failed to extract audio")
                return None

            transcription = self.transcribe_locally(audio_path, status_callback)
            
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