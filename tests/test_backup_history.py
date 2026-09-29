import os
import shutil
import unittest

from backup_history.backup_manager import backup_file
from backup_history.history_manager import record_history, get_history


class BackupHistoryTest(unittest.TestCase):

    def setUp(self):
        self.test_file = "test_sample.txt"

        with open(self.test_file, "w", encoding="utf-8") as file:
            file.write("test data")

    def tearDown(self):
        if os.path.exists(self.test_file):
            os.remove(self.test_file)

        if os.path.exists("backups"):
            shutil.rmtree("backups")

        if os.path.exists("logs"):
            shutil.rmtree("logs")

    def test_backup_success(self):
        backup_path = backup_file(self.test_file)

        self.assertTrue(os.path.exists(backup_path))

    def test_backup_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            backup_file("no_file.txt")

    def test_history_record(self):
        record_history(
            self.test_file,
            "backups/test_sample.txt",
            2,
            "masking",
            "success"
        )

        histories = get_history()

        self.assertEqual(len(histories), 1)
        self.assertEqual(histories[0]["detection_count"], 2)
        self.assertEqual(histories[0]["status"], "success")


if __name__ == "__main__":
    unittest.main()