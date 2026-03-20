from __future__ import annotations

from datetime import time
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import Workbook

from core.loader import load_timetable
from core.types import (
    AnalyzeConfig,
    AppConfig,
    BuildConfig,
    ExportTimetableConfig,
    InputConfig,
    ProjectConfig,
    RawTable,
    ScenarioConfig,
    SolveConfig,
    SolverConfig,
)
from core.validator import validate_inputs


def _build_config() -> AppConfig:
    return AppConfig(
        project=ProjectConfig(name="test", output_dir=Path("outputs/test")),
        input=InputConfig(
            timetable_path=Path("inputs/timetable.xlsx"),
            mileage_path=Path("inputs/mileage.xlsx"),
            timetable_sheet_name="Sheet1",
            mileage_sheet_name="Sheet1",
        ),
        solver=SolverConfig(
            objective_delay_weight=1.0,
            objective_mode="abs",
            arr_arr_headway_seconds=180,
            dep_dep_headway_seconds=180,
            dwell_seconds_at_stops=120,
            big_m=100000,
            tolerance_delay_seconds=7200,
        ),
        scenarios=ScenarioConfig(delays=[], speed_limits=[], interruptions=[]),
        build=BuildConfig(lp_path=Path("outputs/test/model.lp")),
        solve=SolveConfig(
            lp_path=Path("outputs/test/model.lp"),
            solution_path=Path("outputs/test/solution.sol"),
        ),
        export_timetable=ExportTimetableConfig(
            solution_path=Path("outputs/test/solution.sol"),
            timetable_path=Path("outputs/test/adjusted_timetable.xlsx"),
        ),
        analyze=AnalyzeConfig(
            enable_metrics=False,
            enable_plot=False,
            plot_grid=False,
            plot_title="Train Timetable",
            plan_timetable_path=Path("inputs/timetable.xlsx"),
            adjusted_timetable_path=Path("outputs/test/adjusted_timetable.xlsx"),
            metrics_output_path=Path("outputs/test/analysis_metrics.xlsx"),
            plot_output_path=Path("outputs/test/timetable_plot.png"),
            plot_timetable_path=Path("outputs/test/adjusted_timetable.xlsx"),
        ),
    )


class InputNormalizationTest(unittest.TestCase):
    def test_load_timetable_normalizes_headers_and_excel_times(self) -> None:
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "timetable.xlsx"
            workbook = Workbook()
            worksheet = workbook.active
            worksheet.title = "Sheet1"
            worksheet.append(["train_ID", "station", "arrival_time", "departure_time"])
            worksheet.append(["G1", "alpha", time(9, 17), "9:22:00"])
            worksheet.append(["G1", "beta", "9:30:00", None])
            workbook.save(path)

            table = load_timetable(path, "Sheet1")

        self.assertEqual(
            table.headers,
            ["train_id", "station", "arrival_time", "departure_time"],
        )
        self.assertEqual(table.rows[0]["arrival_time"], "09:17:00")
        self.assertEqual(table.rows[0]["departure_time"], "09:22:00")

    def test_validate_inputs_normalizes_single_digit_hour_strings(self) -> None:
        timetable = RawTable(
            headers=["train_id", "station", "arrival_time", "departure_time"],
            rows=[
                {
                    "train_id": "G1",
                    "station": "alpha",
                    "arrival_time": None,
                    "departure_time": "9:22:00",
                },
                {
                    "train_id": "G1",
                    "station": "beta",
                    "arrival_time": "9:30:00",
                    "departure_time": None,
                },
            ],
        )
        mileage = RawTable(
            headers=["station", "mileage"],
            rows=[
                {"station": "alpha", "mileage": "0"},
                {"station": "beta", "mileage": "10"},
            ],
        )

        validated = validate_inputs(_build_config(), timetable, mileage)

        self.assertEqual(validated.timetable_rows[0].departure_time, "09:22:00")
        self.assertEqual(validated.timetable_rows[1].arrival_time, "09:30:00")


if __name__ == "__main__":
    unittest.main()
