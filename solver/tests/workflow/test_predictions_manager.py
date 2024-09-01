import unittest
from unittest.mock import MagicMock, patch, mock_open
from pathlib import Path
from tempfile import TemporaryDirectory
from solver.predictions_manager import PredictionsManager


class TestPredictionsManager(unittest.TestCase):
    def setUp(self):
        self.log_mock = MagicMock()
        self.instance_set = "test_instance"
        self.num_runners = 2
        self.runner_index = 1

        self.temp_dir = TemporaryDirectory()

        predictions_dir = Path(self.temp_dir.name) / "predictions"

        self.predictions_manager = PredictionsManager(
            log=self.log_mock,
            instance_set=self.instance_set,
            num_runners=self.num_runners,
            runner_index=self.runner_index,
            directory=predictions_dir,
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_initialization(self):
        self.assertEqual(self.predictions_manager.predictions_name, "test_instance-1_2")
        self.assertTrue(self.predictions_manager.predictions_dir.exists())
        self.assertFalse(self.predictions_manager.predictions_path.exists())

    @patch("solver.predictions_manager.Path.rename")
    def test_handle_existing_predictions_file(self, rename_mock):
        self.predictions_manager.predictions_path.touch()
        self.predictions_manager._handle_existing_predictions_file()
        rename_mock.assert_called_once()

    def test_write_predictions(self):
        predictions = '{"key": "value"}'
        self.predictions_manager.write_predictions(predictions)
        with self.predictions_manager.predictions_path.open("r") as f:
            content = f.read()
            self.assertEqual(content, predictions)

    @patch("solver.predictions_manager.Path.exists", return_value=True)
    @patch(
        "solver.predictions_manager.Path.open",
        new_callable=mock_open,
        read_data='{"key": "value"}',
    )
    def test_read_predictions(self, mock_open, mock_exists):
        result = self.predictions_manager.read_predictions()
        self.assertEqual(result, '{"key": "value"}')
        mock_exists.assert_called_once()
        mock_open.assert_called_once_with("r")

    @patch("solver.predictions_manager.Path.open", new_callable=mock_open)
    def test_read_predictions_no_file(self, mock_open):
        self.predictions_manager.predictions_path.unlink(missing_ok=True)
        result = self.predictions_manager.read_predictions()
        self.assertIsNone(result)

    @patch("builtins.open", new_callable=mock_open)
    def test_add_prediction(self, mock_open):
        prediction = {"key": "value"}
        PredictionsManager.add_prediction("dummy.jsonl", prediction)
        mock_open.assert_called_once_with("dummy.jsonl", "a")
        mock_open().write.assert_called_once_with('{"key": "value"}\n')

    def test_collect_predictions(self):
        initial_predictions = '{"key": "value"}\n'
        with self.predictions_manager.predictions_path.open("w") as f:
            f.write(initial_predictions)

        output_path = Path(self.temp_dir.name) / "collected_predictions.jsonl"
        self.predictions_manager.collect_predictions(output_path)

        with output_path.open("r") as f:
            collected_predictions = f.read()
            self.assertEqual(collected_predictions, initial_predictions)


if __name__ == "__main__":
    unittest.main()
