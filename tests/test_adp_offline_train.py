import csv
import json
import tempfile
import unittest
from pathlib import Path

from tools import adp_offline_train as trainer


def write_dataset(path: Path, include_all_fields: bool = True) -> None:
    fields = list(trainer.CSV_FIELDS)
    if not include_all_fields:
        fields.remove("iout_a")
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for episode in range(2):
            for step in range(4):
                row = {
                    "episode": episode,
                    "step": step,
                    "vref_v": 12.0,
                    "vin_v": 24.0,
                    "vout_v": 11.0 + step * 0.1,
                    "iin_a": 1.0,
                    "iout_a": 1.0,
                    "iref_applied_a": 2.0,
                }
                writer.writerow({key: value for key, value in row.items() if key in fields})


class AdpOfflineTrainerTest(unittest.TestCase):
    def test_export_has_mcu_shape_and_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dataset = root / "capture.csv"
            output = root / "adp_outer_weights.h"
            write_dataset(dataset)

            transitions, stats = trainer.load_csv(dataset, 20.0)
            args = trainer.build_parser().parse_args(
                [
                    "--dataset",
                    str(dataset),
                    "--ilimit",
                    "20",
                    "--epochs",
                    "1",
                    "--output",
                    str(output),
                ]
            )
            trainer.train(transitions, args, stats)

            header = output.read_text(encoding="ascii")
            report = json.loads(output.with_suffix(".json").read_text())
            self.assertIn("adp_actor_input[16][7]", header)
            self.assertIn("adp_critic_input[16][8]", header)
            self.assertEqual(report["shape"]["state_count"], 7)
            self.assertFalse(report["online_training"])
            self.assertRegex(report["checksum"], r"^0x[0-9A-F]{8}$")

    def test_missing_field_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            dataset = Path(directory) / "invalid.csv"
            write_dataset(dataset, include_all_fields=False)
            with self.assertRaises(ValueError):
                trainer.load_csv(dataset, 20.0)


if __name__ == "__main__":
    unittest.main()
