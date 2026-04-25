import os
import time
from typing import Dict, Any

# Global in-memory session cache
# Format: { session_id: {"excel_path": str, "data": list_of_dicts, "generated_at": float} }
session_data: Dict[str, Any] = {}

# Temporary directory for reports
REPORTS_TEMP_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "temp", "reports"))

def init_reports_dir():
    """Initializes the reports temporary directory."""
    if not os.path.exists(REPORTS_TEMP_DIR):
        os.makedirs(REPORTS_TEMP_DIR, exist_ok=True)
        print(f"Created reports directory at {REPORTS_TEMP_DIR}")

def cleanup_old_reports(max_age_seconds: int = 3600):
    """Removes files older than max_age_seconds from the reports directory."""
    now = time.time()
    if not os.path.exists(REPORTS_TEMP_DIR):
        return
        
    for filename in os.listdir(REPORTS_TEMP_DIR):
        filepath = os.path.join(REPORTS_TEMP_DIR, filename)
        if os.path.isfile(filepath):
            if now - os.path.getmtime(filepath) > max_age_seconds:
                try:
                    os.remove(filepath)
                except Exception:
                    pass
