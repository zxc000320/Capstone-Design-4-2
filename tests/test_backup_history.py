import os
import shutil
import unittest

from backup_history.history_manager import record_history, get_history


class HistoryTest(unittest.TestCase):

    def tearDown(self):
        if os.path.exists("logs"):
            shutil.rmtree("logs")

    def test_history_record(self):
        record_history(
            "test_sample.txt",
            "output/test_sample_masked.txt",
            2,
            "masking",
            "success"
        )

        histories = get_history()

        self.assertEqual(len(histories), 1)
        self.assertEqual(
            histories[0]["output_path"],
            "output/test_sample_masked.txt"
        )
        self.assertEqual(histories[0]["detection_count"], 2)
        self.assertEqual(histories[0]["processing_type"], "masking")
        self.assertEqual(histories[0]["status"], "success")

    def test_get_history_when_empty(self):
        histories = get_history()

        self.assertEqual(histories, [])


if __name__ == "__main__":
    unittest.main()