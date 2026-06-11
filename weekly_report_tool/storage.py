import os
import json
import shutil
import zipfile
from typing import Optional, List
from datetime import datetime
from .models import TeamConfig, TeamSummary, WeeklyReport


class StorageManager:
    def __init__(self, base_dir: str = "."):
        self.base_dir = base_dir
        self.config_file = os.path.join(base_dir, ".weekly_report", "config.json")
        self.data_dir = os.path.join(base_dir, ".weekly_report", "data")
        self.summary_dir = os.path.join(base_dir, ".weekly_report", "summaries")
        self.versions_dir = os.path.join(base_dir, ".weekly_report", "versions")
        self.export_dir = os.path.join(base_dir, "weekly_exports")
        self._ensure_dirs()

    def _ensure_dirs(self):
        os.makedirs(self.data_dir, exist_ok=True)
        os.makedirs(self.summary_dir, exist_ok=True)
        os.makedirs(self.versions_dir, exist_ok=True)
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

    def save_version(self, week_start: str, member_name: str) -> bool:
        report_file = self._get_report_file(week_start, member_name)
        if not os.path.exists(report_file):
            return False
        safe_week = week_start.replace("-", "")
        safe_name = member_name.replace(" ", "_")
        version_dir = os.path.join(self.versions_dir, f"{safe_week}_{safe_name}")
        os.makedirs(version_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        version_file = os.path.join(version_dir, f"v_{timestamp}.json")
        counter = 1
        while os.path.exists(version_file):
            version_file = os.path.join(version_dir, f"v_{timestamp}_{counter}.json")
            counter += 1
        shutil.copy2(report_file, version_file)
        return True

    def list_versions(self, week_start: str, member_name: str) -> List[dict]:
        safe_week = week_start.replace("-", "")
        safe_name = member_name.replace(" ", "_")
        version_dir = os.path.join(self.versions_dir, f"{safe_week}_{safe_name}")
        if not os.path.isdir(version_dir):
            return []
        versions = []
        for fname in sorted(os.listdir(version_dir), reverse=True):
            if fname.startswith("v_") and fname.endswith(".json"):
                fpath = os.path.join(version_dir, fname)
                try:
                    with open(fpath, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    versions.append({
                        "version_id": fname[2:-5],
                        "filepath": fpath,
                        "submitted_at": data.get("submitted_at", ""),
                        "item_count": len(data.get("items", [])),
                        "member_name": data.get("member_name", member_name)
                    })
                except (json.JSONDecodeError, IOError):
                    continue
        return versions

    def rollback_report(self, week_start: str, member_name: str, version_id: str) -> bool:
        safe_week = week_start.replace("-", "")
        safe_name = member_name.replace(" ", "_")
        version_dir = os.path.join(self.versions_dir, f"{safe_week}_{safe_name}")
        version_file = os.path.join(version_dir, f"v_{version_id}.json")
        if not os.path.exists(version_file):
            return False
        report_file = self._get_report_file(week_start, member_name)
        shutil.copy2(version_file, report_file)
        summary_file = self._get_summary_file(week_start)
        if os.path.exists(summary_file):
            os.remove(summary_file)
        return True

    def create_archive(self, week_start: str, team_name: str = "",
                       output_dir: Optional[str] = None,
                       create_zip: bool = False) -> str:
        safe_week = week_start.replace("-", "")
        archive_name = f"{team_name}周报归档_{week_start}" if team_name else f"周报归档_{week_start}"
        archive_name = archive_name.replace(" ", "_")

        if output_dir is None:
            output_dir = os.path.join(self.base_dir, "weekly_archives")
        os.makedirs(output_dir, exist_ok=True)

        archive_path = os.path.join(output_dir, archive_name)
        if os.path.exists(archive_path):
            shutil.rmtree(archive_path)

        reports_dir = os.path.join(archive_path, "原始周报")
        versions_dir_out = os.path.join(archive_path, "历史版本")
        summary_dir_out = os.path.join(archive_path, "汇总摘要")
        exports_dir_out = os.path.join(archive_path, "导出文件")
        os.makedirs(reports_dir, exist_ok=True)
        os.makedirs(versions_dir_out, exist_ok=True)
        os.makedirs(summary_dir_out, exist_ok=True)
        os.makedirs(exports_dir_out, exist_ok=True)

        if os.path.isdir(self.data_dir):
            for fname in os.listdir(self.data_dir):
                if fname.startswith(safe_week) and fname.endswith(".json"):
                    shutil.copy2(os.path.join(self.data_dir, fname),
                                 os.path.join(reports_dir, fname))

        if os.path.isdir(self.versions_dir):
            for dname in os.listdir(self.versions_dir):
                if dname.startswith(safe_week):
                    src = os.path.join(self.versions_dir, dname)
                    dst = os.path.join(versions_dir_out, dname)
                    if os.path.isdir(src):
                        shutil.copytree(src, dst)

        summary_file = self._get_summary_file(week_start)
        if os.path.exists(summary_file):
            shutil.copy2(summary_file, os.path.join(summary_dir_out, os.path.basename(summary_file)))

        if os.path.isdir(self.export_dir):
            week_tag = safe_week
            for fname in os.listdir(self.export_dir):
                if week_tag in fname:
                    shutil.copy2(os.path.join(self.export_dir, fname),
                                 os.path.join(exports_dir_out, fname))

        config_file = self.config_file
        if os.path.exists(config_file):
            shutil.copy2(config_file, os.path.join(archive_path, "config.json"))

        readme_path = os.path.join(archive_path, "README.txt")
        with open(readme_path, "w", encoding="utf-8") as f:
            f.write(f"团队周报归档\n")
            f.write(f"周起始日期: {week_start}\n")
            f.write(f"归档时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"\n目录说明:\n")
            f.write(f"  原始周报/    各成员周报 JSON 数据\n")
            f.write(f"  历史版本/    各成员周报历史版本\n")
            f.write(f"  汇总摘要/    TeamSummary 摘要文件\n")
            f.write(f"  导出文件/    导出的邮件/群公告/Markdown 文件\n")
            f.write(f"  config.json  团队配置\n")

        if create_zip:
            zip_path = archive_path + ".zip"
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for root, dirs, files in os.walk(archive_path):
                    for fname in files:
                        full_path = os.path.join(root, fname)
                        arcname = os.path.relpath(full_path, os.path.dirname(archive_path))
                        zf.write(full_path, arcname)
            return zip_path

        return archive_path
