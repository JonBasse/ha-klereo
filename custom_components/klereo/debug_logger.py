import os
import datetime

LOG_FILE = "klereo_debug.log"

def log_to_file(message):
    """Write a message to the debug log file."""
    try:
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(LOG_FILE, "a") as f:
            f.write(f"[{timestamp}] {message}\n")
    except Exception:
        pass # Fallback if file access fails
