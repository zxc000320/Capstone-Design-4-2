import json
import warnings
from datetime import datetime
from pathlib import Path


LOG_DIR = Path("logs")
LOG_FILE = LOG_DIR / "history.jsonl"


def _valid_history(history):
    if not isinstance(history, dict):
        return False
    if not all(isinstance(history.get(key), str)
               for key in ("timestamp", "original_filename", "processing_type", "status")):
        return False
    if "output_path" not in history:
        return False
    if history["output_path"] is not None and not isinstance(history["output_path"], str):
        return False
    count = history.get("detection_count")
    if type(count) is not int or count < 0:
        return False
    if history["processing_type"] not in ("check", "masking"):
        return False
    if history["status"] not in ("success", "failed"):
        return False
    error = history.get("error_message")
    return error is None or isinstance(error, str)


def record_history(
    original_file,
    output_path,
    detection_count,
    processing_type,
    status,
    error_message=None
):
    LOG_DIR.mkdir(exist_ok=True)

    history = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "original_filename": Path(original_file).name,
        "output_path": str(output_path) if output_path is not None else None,
        "detection_count": detection_count,
        "processing_type": processing_type,
        "status": status,
        "error_message": error_message
    }

    # Serialize first so an invalid argument cannot leave a partial JSON row.
    payload = (json.dumps(history, ensure_ascii=False) + "\n").encode("utf-8")
    with LOG_FILE.open("a+b") as file:
        file.seek(0, 2)
        prefix = b""
        if file.tell():
            file.seek(-1, 2)
            if file.read(1) != b"\n":
                prefix = b"\n"
        # Preserve all existing bytes, including a truncated final record.
        file.write(prefix + payload)

    return history


def get_history():
    if not LOG_FILE.exists():
        return []

    histories = []

    with LOG_FILE.open("rb") as file:
        for line_number, line in enumerate(file, 1):
            if not line.strip():
                continue
            try:
                history = json.loads(line.decode("utf-8"))
                if not _valid_history(history):
                    raise ValueError("Invalid history fields")
            except (UnicodeDecodeError, ValueError):
                warnings.warn(
                    f"Skipped invalid history record at line {line_number}.",
                    RuntimeWarning,
                    stacklevel=2,
                )
                continue
            histories.append(history)

    return histories
