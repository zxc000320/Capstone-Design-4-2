import os
import shutil
from datetime import datetime


def backup_file(file_path):
    backup_dir = "backups"

    os.makedirs(backup_dir, exist_ok=True)

    filename = os.path.basename(file_path)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    backup_filename = f"{timestamp}_{filename}"
    backup_path = os.path.join(backup_dir, backup_filename)

    shutil.copy2(file_path, backup_path)

    return backup_path