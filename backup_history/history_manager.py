import json
from datetime import datetime
from pathlib import Path


def record_history(
    original_file,
    backup_path,
    detection_count,
    processing_type,
    status,
    error_message=None
):
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    log_file = log_dir / "history.jsonl"

    history = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "original_filename": Path(original_file).name,
        "backup_path": str(backup_path),
        "detection_count": detection_count,
        "processing_type": processing_type,
        "status": status,
        "error_message": error_message
    }

    with log_file.open("a", encoding="utf-8") as file:
        file.write(json.dumps(history, ensure_ascii=False) + "\n")

    return history