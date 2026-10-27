import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from backup_history import history_manager
from backup_history.history_manager import record_history, get_history


class HistoryTest(unittest.TestCase):

    def setUp(self):
        temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        self.work_dir = Path(temporary_directory.name)
        self.log_dir = self.work_dir / "logs"
        log_paths = patch.multiple(
            history_manager,
            LOG_DIR=self.log_dir,
            LOG_FILE=self.log_dir / "history.jsonl",
        )
        log_paths.start()
        self.addCleanup(log_paths.stop)

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

    def test_failed_history_record(self):
        history = record_history(
            "sample.txt",
            "output/sample_masked.txt",
            2,
            "masking",
            "failed",
            error_message="처리본 저장 실패",
        )

        self.assertEqual(get_history(), [history])
        self.assertEqual(history["status"], "failed")
        self.assertEqual(history["error_message"], "처리본 저장 실패")

    def test_multiple_histories_are_appended_in_order(self):
        first = record_history(
            "first.txt", "output/first_masked.txt", 1, "masking", "success"
        )
        second = record_history(
            "second.txt", "output/second_masked.txt", 3, "masking", "success"
        )

        self.assertEqual(get_history(), [first, second])

    def test_record_preserves_original_and_output_files(self):
        original = self.work_dir / "원본.txt"
        output = self.work_dir / "처리본.txt"
        original_bytes = "테스트 원본\n".encode("utf-8")
        output_bytes = "테스트 처리본\n".encode("utf-8")
        original.write_bytes(original_bytes)
        output.write_bytes(output_bytes)

        history = record_history(original, output, 0, "masking", "success")

        self.assertEqual(original.read_bytes(), original_bytes)
        self.assertEqual(output.read_bytes(), output_bytes)
        self.assertEqual(get_history(), [history])
        self.assertEqual(history["original_filename"], "원본.txt")
        self.assertEqual(history["output_path"], str(output))
        self.assertEqual(history["detection_count"], 0)
        self.assertIsNone(history["error_message"])


if __name__ == "__main__":
    unittest.main()
