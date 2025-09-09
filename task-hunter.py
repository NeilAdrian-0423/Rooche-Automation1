import psutil
import os

def list_python_scripts():
    print("🔍 Checking running Python scripts...\n")
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            if proc.info['name'] and "python" in proc.info['name'].lower():
                cmdline = proc.info['cmdline']
                if cmdline and len(cmdline) > 1:
                    script = cmdline[1]  # usually the .py file
                    print(f"PID {proc.info['pid']} -> {os.path.basename(script)} | Full cmd: {' '.join(cmdline)}")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

if __name__ == "__main__":
    list_python_scripts()
