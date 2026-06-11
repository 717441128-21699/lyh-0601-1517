import os
import json
from typing import Optional
from datetime import datetime
from .models import TeamConfig, TeamSummary, WeeklyReport


class StorageManager:
    def __init__(self, base_dir: str = "."):
        self.base_dir = base_dir
        self.config_file = os.path.join(base_dir, ".weekly_report", "config.json")
        self.data_dir = os.path.join(base_dir, ".weekly_report", "data")
        self.summary_dir = os.path.join(base_dir, ".weekly_report", "summaries")
        self.export_dir = os.path.join(base_dir, "weekly_exports")
        self._ensure_dirs()

    def _ensure_dirs(self):
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.summary_dir, exist_ok=True)
        os.makedirs(self.export_dir, exist_ok=True)

    def is_initialized(self) -> bool:
        return os.path.exists(self.config_file)

    def save_config(self, config: TeamConfig):
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(config.to_dict(), f, ensure_ascii=False, indent=2)

    def load_config(self) -> Optional[TeamConfig]:
        if not self.is_initialized():
            return None
        with open(self.config_file, "r", encoding="utf-8") as f:
            return TeamConfig.from_dict(json.load(f))

    def _get_report_file(self, week_start: str, member_name: str) -> str:
        safe_week = week_start.replace("-", "")
        safe_name = member_name.replace(" ", "_")
        return os.path.join(self.data_dir, f"{safe_week}_{safe_name}.json")

    def save_report(self, report: WeeklyReport):
        filepath = self._get_report_file(report.week_start, report.member_name)
        if not report.submitted_at:
            report.submitted_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, ensure_ascii=False, indent=2)

    def has_report(self, week_start: str, member_name: str) -> bool:
        filepath = self._get_report_file(week_start, member_name)
        return os.path.exists(filepath)

    def load_report(self, week_start: str, member_name: str) -> Optional[WeeklyReport]:
        filepath = self._get_report_file(week_start, member_name)
        if not os.path.exists(filepath):
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            return WeeklyReport.from_dict(json.load(f))

    def load_all_reports_for_week(self, week_start: str) -> dict:
        reports = {}
        safe_week = week_start.replace("-", "")
        if os.path.exists(self.data_dir):
            for filename in os.listdir(self.data_dir):
                if filename.startswith(safe_week) and filename.endswith(".json"):
                    filepath = os.path.join(self.data_dir, filename)
                    with open(filepath, "r", encoding="utf-8") as f:
                        report = WeeklyReport.from_dict(json.load(f))
                        reports[report.member_name] = report
        return reports

    def _get_summary_file(self, week_start: str) -> str:
        safe_week = week_start.replace("-", "")
        return os.path.join(self.summary_dir, f"summary_{safe_week}.json")

    def save_summary(self, summary: TeamSummary):
        filepath = self._get_summary_file(summary.week_start)
        if not summary.generated_at:
            summary.generated_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(summary.to_dict(), f, ensure_ascii=False, indent=2)

    def load_summary(self, week_start: str) -> Optional[TeamSummary]:
        filepath = self._get_summary_file(week_start)
        if not os.path.exists(filepath):
            return None
        with open(filepath, "r", encoding="utf-8") as f:
            return TeamSummary.from_dict(json.load(f))

    def get_export_path(self, week_start: str, filename: str) -> str:
        safe_week = week_start.replace("-", "")
        name, ext = os.path.splitext(filename)
        return os.path.join(self.export_dir, f"{name}_{safe_week}{ext}")
