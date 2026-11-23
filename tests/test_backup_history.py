import json
import tempfile
import unittest
import warnings
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

    def test_check_only_history_without_output(self):
        original = self.work_dir / "sample.txt"
        original_bytes = b"sample input\n"
        original.write_bytes(original_bytes)

        history = record_history(original, None, 2, "check", "success")

        self.assertIsNone(history["output_path"])
        self.assertEqual(get_history(), [history])
        self.assertEqual(history["processing_type"], "check")
        self.assertEqual(history["status"], "success")
        self.assertEqual(history["detection_count"], 2)
        stored = json.loads(history_manager.LOG_FILE.read_text(encoding="utf-8"))
        self.assertIsNone(stored["output_path"])
        self.assertEqual(original.read_bytes(), original_bytes)
        self.assertEqual(
            {path.relative_to(self.work_dir).as_posix()
             for path in self.work_dir.rglob("*") if path.is_file()},
            {"sample.txt", "logs/history.jsonl"},
        )

    def test_failed_history_without_output(self):
        history = record_history(
            "sample.txt", None, 2, "masking", "failed",
            error_message="처리본 경로 결정 실패",
        )

        self.assertEqual(get_history(), [history])
        self.assertIsNone(history["output_path"])
        self.assertEqual(history["status"], "failed")
        self.assertEqual(history["error_message"], "처리본 경로 결정 실패")

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

    def test_corrupt_lines_preserve_valid_records_and_file(self):
        first = record_history("first.txt", None, 0, "check", "success")
        with history_manager.LOG_FILE.open("ab") as f:
            f.write(b'\n{"private": "SECRET"\n\xff\n[]\n')
        second = record_history("second.txt", None, 1, "check", "success")
        before = history_manager.LOG_FILE.read_bytes()
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.assertEqual(get_history(), [first, second])
        self.assertEqual(len(caught), 3)
        self.assertTrue(all(w.category is RuntimeWarning for w in caught))
        self.assertEqual([str(w.message) for w in caught], [
            f"Skipped invalid history record at line {n}." for n in (3, 4, 5)
        ])
        self.assertNotIn("SECRET", str([w.message for w in caught]))
        self.assertEqual(history_manager.LOG_FILE.read_bytes(), before)

    def test_all_invalid_returns_empty_with_warning(self):
        self.log_dir.mkdir()
        history_manager.LOG_FILE.write_text('{"unfinished":', encoding="utf-8")
        with self.assertWarns(RuntimeWarning):
            self.assertEqual(get_history(), [])

    def test_blank_lines_do_not_warn(self):
        self.log_dir.mkdir()
        history_manager.LOG_FILE.write_text("\n  \n", encoding="utf-8")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.assertEqual(get_history(), [])
        self.assertEqual(caught, [])

    def test_append_after_truncated_tail_preserves_new_record(self):
        first = record_history("first.txt", None, 0, "check", "success")
        with history_manager.LOG_FILE.open("ab") as f:
            f.write(b'{"unfinished":')
        before = history_manager.LOG_FILE.read_bytes()
        second = record_history("second.txt", None, 1, "check", "success")
        self.assertTrue(history_manager.LOG_FILE.read_bytes().startswith(before + b"\n"))
        with self.assertWarns(RuntimeWarning):
            self.assertEqual(get_history(), [first, second])

    def test_append_after_valid_tail_without_newline(self):
        first = record_history("first.txt", None, 0, "check", "success")
        history_manager.LOG_FILE.write_bytes(history_manager.LOG_FILE.read_bytes().rstrip(b"\n"))
        second = record_history("second.txt", None, 1, "check", "success")
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            self.assertEqual(get_history(), [first, second])
        self.assertEqual(caught, [])

    def test_invalid_fields_are_skipped(self):
        valid = record_history("valid.txt", None, 0, "check", "success")
        invalid = [{}, {k: v for k, v in valid.items() if k != "output_path"}]
        for key, value in (
            ("timestamp", 123), ("original_filename", []),
            ("output_path", 123), ("detection_count", True),
            ("detection_count", -1), ("detection_count", "2"),
            ("processing_type", []), ("processing_type", "unknown"),
            ("status", {}), ("status", "unknown"), ("error_message", []),
        ):
            invalid.append({**valid, key: value})
        for row in invalid:
            with self.subTest(row=row):
                history_manager.LOG_FILE.write_text(
                    "\n".join(json.dumps(r) for r in (valid, row, valid)) + "\n",
                    encoding="utf-8",
                )
                before = history_manager.LOG_FILE.read_bytes()
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    self.assertEqual(get_history(), [valid, valid])
                self.assertEqual(len(caught), 1)
                self.assertEqual(str(caught[0].message), "Skipped invalid history record at line 2.")
                self.assertEqual(history_manager.LOG_FILE.read_bytes(), before)

    def test_optional_error_and_extra_fields_remain_compatible(self):
        row = record_history("valid.txt", None, 0, "check", "success")
        row.pop("error_message")
        row["extra"] = "future field"
        history_manager.LOG_FILE.write_text(json.dumps(row) + "\n", encoding="utf-8")
        self.assertEqual(get_history(), [row])

    def test_io_errors_are_not_hidden(self):
        with patch.object(Path, "open", side_effect=PermissionError("denied")):
            with patch.object(Path, "exists", return_value=True):
                with self.assertRaises(PermissionError):
                    get_history()


if __name__ == "__main__":
    unittest.main()
