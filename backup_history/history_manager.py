import json
from datetime import datetime
from pathlib import Path


LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "history.jsonl"


def record_history(
    original_file,
    backup_path,
    detection_count,
    processing_type,
    status,
    error_message=None
):
    LOG_DIR.mkdir(exist_ok=True)

    history = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "original_filename": Path(original_file).name,
        "backup_path": str(backup_path),
        "detection_count": detection_count,
        "processing_type": processing_type,
        "status": status,
        "error_message": error_message
    }

    with LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(json.dumps(history, ensure_ascii=False) + "\n")

    return history


def get_history():
    if not LOG_FILE.exists():
        return []

    histories = []

    with LOG_FILE.open("r", encoding="utf-8") as file:
        for line in file:
            if line.strip():
                histories.append(json.loads(line))

    return histories