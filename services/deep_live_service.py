import os
import json
import subprocess
import logging
import signal
import threading
import queue
import time

logger = logging.getLogger(__name__)


class DeepLiveService:
    def __init__(self):
        self.process = None
        self.log_queue = queue.Queue()

    def _reader_thread(self, stream, level=logging.INFO):
        """Read a subprocess stream and log line-by-line."""
        try:
            for line in iter(stream.readline, ''):
                line = line.strip()
                if not line:
                    continue
                logger.log(level, f"Deep Live: {line}")
                self.log_queue.put(line)
        except Exception as e:
            logger.error(f"Error reading process stream: {e}")
        finally:
            stream.close()

    def _wait_for_ready(self, timeout=120, retries=2):
        """Wait until Deep Live fully initializes and starts processing."""
        init_phrases = [
            "DEEP_LIVE_CAM_READY",
            "Camera initialized",
            "Virtual camera started",
            "Frame processors loaded",
            "Source image loaded and face detected successfully"
        ]
        active_phrases = [
            "Starting main processing loop",
            "Face detection failed for target or source"
        ]
        error_phrases = [
            "error: unrecognized arguments",  # For argparse errors
            "Fatal error in Deep Live Cam",  # From main() exception
            "Failed to open camera",  # Camera initialization failure
            "Failed to load source image",  # Source image loading failure
            "Failed to capture frame from camera"  # Frame capture failure
        ]

        for attempt in range(1, retries + 1):
            logger.info(f"Deep Live readiness check attempt {attempt}/{retries}")

            start = time.time()
            init_detected = False

            # Phase 1: Wait for initialization
            while time.time() - start < timeout:
                try:
                    line = self.log_queue.get(timeout=10)
                    # Check for error messages first
                    if any(p in line.lower() for p in error_phrases) or "ERROR" in line:
                        logger.error(f"Error detected in Deep Live logs: {line.strip()}")
                        self.stop_deeplive()
                        raise RuntimeError(f"Deep Live failed with error: {line.strip()}")
                    # Check for initialization phrases
                    if any(p in line for p in init_phrases):
                        logger.info(f"Deep Live init detected: {line.strip()}")
                        init_detected = True
                        break
                except queue.Empty:
                    continue

            if not init_detected:
                logger.warning("Initialization phrases not detected in time")
                continue  # Retry next attempt

            # Phase 2: After init, wait up to 30s for active processing
            active_start = time.time()
            while time.time() - active_start < 30:
                try:
                    line = self.log_queue.get(timeout=5)
                    # Check for error messages
                    if any(p in line.lower() for p in error_phrases) or "ERROR" in line:
                        logger.error(f"Error detected in Deep Live logs: {line.strip()}")
                        self.stop_deeplive()
                        raise RuntimeError(f"Deep Live failed with error: {line.strip()}")
                    # Check for active processing phrases
                    if any(p in line for p in active_phrases):
                        logger.info(f"Deep Live active processing detected: {line.strip()}")
                        return True
                except queue.Empty:
                    continue

            logger.warning("Active processing not detected after initialization")

        # If all retries fail
        logger.error("Deep Live failed to signal readiness after retries, stopping process")
        self.stop_deeplive()
        raise TimeoutError("Deep Live did not signal readiness in time")


    def start_deeplive(self, deeplive_dir: str, image_path: str, settings: dict):
        """Start Deep Live Cam CLI with dynamic args."""
        if self.process is not None and self.process.poll() is None:
            logger.info("Deep Live already running — terminating before restart")
            self.stop_deeplive()

        try:
            venv_python = os.path.join(
                deeplive_dir,
                "venv",
                "Scripts" if os.name == "nt" else "bin",
                "python.exe" if os.name == "nt" else "python3"
            )
            run_py = os.path.join(deeplive_dir, "run_deeplive.py")

            if not os.path.exists(venv_python):
                raise FileNotFoundError(f"Python not found: {venv_python}")
            if not os.path.exists(run_py):
                raise FileNotFoundError(f"run_deeplive.py not found: {run_py}")

            # Update switch_states.json
            switch_file = os.path.join(deeplive_dir, "switch_states.json")
            try:
                with open(switch_file, "r") as f:
                    data = json.load(f)
            except (FileNotFoundError, json.JSONDecodeError):
                data = {}

            data.update({
                "mouth_mask": settings.get("mouth_mask", False),
                "many_faces": settings.get("many_faces", True),
                "camera_index": settings.get("camera_index"),
                "source_path": image_path if image_path and os.path.exists(image_path) else data.get("source_path")
            })

            with open(switch_file, "w") as f:
                json.dump(data, f, indent=4)

            logger.debug(f"Updated {switch_file}: {json.dumps(data, indent=2)}")

            # Build command
            command = [venv_python, run_py]
            if settings.get("camera_index") is not None:
                command.append(str(settings["camera_index"]))
            if image_path and os.path.exists(image_path):
                command.append(image_path)

            # Launch process
            self.process = subprocess.Popen(
                command,
                cwd=deeplive_dir,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1  # line-buffered
            )

            logger.info(f"Started Deep Live (PID: {self.process.pid})")

            # Start reader threads for both stdout and stderr
            threading.Thread(target=self._reader_thread, args=(self.process.stdout,), daemon=True).start()
            threading.Thread(target=self._reader_thread, args=(self.process.stderr, logging.ERROR), daemon=True).start()

            # Give the process a moment to start up
            time.sleep(2)

            # Wait until ready or fail fast - using startup_delay from settings
            self._wait_for_ready(timeout=settings.get("startup_delay", 15))

            if self.process.poll() is not None:
                raise RuntimeError(f"Deep Live exited early with code {self.process.returncode}")

            return self.process

        except Exception as e:
            logger.error(f"Failed to start Deep Live: {e}")
            # Clean up if process was created but failed
            if self.process and self.process.poll() is None:
                try:
                    self.process.terminate()
                except:
                    pass
            self.process = None
            raise

    def stop_deeplive(self):
        """Terminate running Deep Live process if present."""
        if self.process is None:
            logger.warning("No Deep Live process to stop")
            return

        try:
            if os.name == "nt":
                try:
                    self.process.send_signal(signal.CTRL_BREAK_EVENT)
                except Exception:
                    logger.debug("CTRL_BREAK_EVENT failed, using terminate()")
                    self.process.terminate()
            else:
                self.process.terminate()

            self.process.wait(timeout=3)
            logger.info(f"Terminated Deep Live (PID: {self.process.pid})")

        except subprocess.TimeoutExpired:
            logger.warning("Deep Live did not exit in time, killing")
            self.process.kill()
            self.process.wait(timeout=3)
        except Exception as e:
            logger.error(f"Error stopping Deep Live: {e}")
        finally:
            self.process = None

    def is_running(self):
        """Check if Deep Live process is currently running."""
        return self.process is not None and self.process.poll() is None