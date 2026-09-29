import os
import shutil
from datetime import datetime


def backup_file(file_path):
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"원본 파일을 찾을 수 없습니다: {file_path}")

    backup_dir = "backups"

    try:
        os.makedirs(backup_dir, exist_ok=True)

        filename = os.path.basename(file_path)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        backup_filename = f"{timestamp}_{filename}"
        backup_path = os.path.join(backup_dir, backup_filename)

        shutil.copy2(file_path, backup_path)

        return backup_path

    except Exception as e:
        raise RuntimeError(f"파일 백업 중 오류가 발생했습니다: {e}")