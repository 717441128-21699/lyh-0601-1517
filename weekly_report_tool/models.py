from dataclasses import dataclass, field, asdict
from typing import List, Dict, Optional, Any
from datetime import datetime
import json
import os
from enum import Enum


class ItemType(Enum):
    COMPLETED = "completed"
    PLANNED = "planned"
    RISK = "risk"
    HELP = "help"


class ItemStatus(Enum):
    NORMAL = "normal"
    DELAYED = "delayed"
    BLOCKED = "blocked"


@dataclass
class Member:
    name: str
    role: str = ""
    email: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "Member":
        return cls(**data)


@dataclass
class Project:
    name: str
    owner: str = ""
    description: str = ""

    def to_dict(self) -> Dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict) -> "Project":
        return cls(**data)


@dataclass
class ReportItem:
    item_type: ItemType
    content: str
    project: str = ""
    status: ItemStatus = ItemStatus.NORMAL
    delay_reason: str = ""
    deadline: str = ""
    assignee: str = ""

    def to_dict(self) -> Dict:
        data = asdict(self)
        data["item_type"] = self.item_type.value
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: Dict) -> "ReportItem":
        item_type = ItemType(data.get("item_type", "completed"))
        status = ItemStatus(data.get("status", "normal"))
        return cls(
            item_type=item_type,
            content=data.get("content", ""),
            project=data.get("project", ""),
            status=status,
            delay_reason=data.get("delay_reason", ""),
            deadline=data.get("deadline", ""),
            assignee=data.get("assignee", "")
        )


@dataclass
class WeeklyReport:
    member_name: str
    week_start: str
    week_end: str
    submitted_at: str = ""
    items: List[ReportItem] = field(default_factory=list)
    notes: str = ""

    def to_dict(self) -> Dict:
        return {
            "member_name": self.member_name,
            "week_start": self.week_start,
            "week_end": self.week_end,
            "submitted_at": self.submitted_at,
            "items": [item.to_dict() for item in self.items],
            "notes": self.notes
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "WeeklyReport":
        items = [ReportItem.from_dict(i) for i in data.get("items", [])]
        return cls(
            member_name=data.get("member_name", ""),
            week_start=data.get("week_start", ""),
            week_end=data.get("week_end", ""),
            submitted_at=data.get("submitted_at", ""),
            items=items,
            notes=data.get("notes", "")
        )

    def get_items_by_type(self, item_type: ItemType) -> List[ReportItem]:
        return [i for i in self.items if i.item_type == item_type]

    def get_delayed_items(self) -> List[ReportItem]:
        return [i for i in self.items if i.status == ItemStatus.DELAYED]

    def get_blocked_items(self) -> List[ReportItem]:
        return [i for i in self.items if i.status == ItemStatus.BLOCKED]


@dataclass
class TeamConfig:
    team_name: str
    members: List[Member] = field(default_factory=list)
    projects: List[Project] = field(default_factory=list)
    default_week_start: str = "monday"

    def to_dict(self) -> Dict:
        return {
            "team_name": self.team_name,
            "members": [m.to_dict() for m in self.members],
            "projects": [p.to_dict() for p in self.projects],
            "default_week_start": self.default_week_start
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "TeamConfig":
        members = [Member.from_dict(m) for m in data.get("members", [])]
        projects = [Project.from_dict(p) for p in data.get("projects", [])]
        return cls(
            team_name=data.get("team_name", ""),
            members=members,
            projects=projects,
            default_week_start=data.get("default_week_start", "monday")
        )

    def member_names(self) -> List[str]:
        return [m.name for m in self.members]

    def project_names(self) -> List[str]:
        return [p.name for p in self.projects]


@dataclass
class TeamSummary:
    week_start: str
    week_end: str
    generated_at: str = ""
    manual_notes: str = ""
    reports: Dict[str, WeeklyReport] = field(default_factory=dict)
    follow_up_members: List[str] = field(default_factory=list)
    missing_members: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            "week_start": self.week_start,
            "week_end": self.week_end,
            "generated_at": self.generated_at,
            "manual_notes": self.manual_notes,
            "reports": {k: v.to_dict() for k, v in self.reports.items()},
            "follow_up_members": self.follow_up_members,
            "missing_members": self.missing_members
        }

    @classmethod
    def from_dict(cls, data: Dict) -> "TeamSummary":
        reports = {k: WeeklyReport.from_dict(v) for k, v in data.get("reports", {}).items()}
        return cls(
            week_start=data.get("week_start", ""),
            week_end=data.get("week_end", ""),
            generated_at=data.get("generated_at", ""),
            manual_notes=data.get("manual_notes", ""),
            reports=reports,
            follow_up_members=data.get("follow_up_members", []),
            missing_members=data.get("missing_members", [])
        )

    def add_report(self, report: WeeklyReport):
        self.reports[report.member_name] = report

    def get_all_items_by_type(self, item_type: ItemType) -> List[ReportItem]:
        all_items = []
        for report in self.reports.values():
            all_items.extend(report.get_items_by_type(item_type))
        return all_items

    def get_all_delayed_items(self) -> List[ReportItem]:
        items = []
        for report in self.reports.values():
            items.extend(report.get_delayed_items())
        return items

    def get_all_blocked_items(self) -> List[ReportItem]:
        items = []
        for report in self.reports.values():
            items.extend(report.get_blocked_items())
        return items

    def get_items_by_project(self, project_name: str) -> List[ReportItem]:
        items = []
        for report in self.reports.values():
            for item in report.items:
                if item.project == project_name:
                    items.append(item)
        return items

    def group_items_by_project(self) -> Dict[str, List[ReportItem]]:
        groups: Dict[str, List[ReportItem]] = {}
        for report in self.reports.values():
            for item in report.items:
                project = item.project or "未分类"
                if project not in groups:
                    groups[project] = []
                groups[project].append(item)
        return groups

    def group_items_by_member_and_type(self) -> Dict[str, Dict[ItemType, List[ReportItem]]]:
        groups: Dict[str, Dict[ItemType, List[ReportItem]]] = {}
        for member_name, report in self.reports.items():
            if member_name not in groups:
                groups[member_name] = {}
            for itype in ItemType:
                groups[member_name][itype] = report.get_items_by_type(itype)
        return groups

    def group_items_by_owner(self, projects: List[Project]) -> Dict[str, Dict[str, List[ReportItem]]]:
        owner_groups: Dict[str, Dict[str, List[ReportItem]]] = {}
        project_owner_map: Dict[str, str] = {}
        for p in projects:
            if p.owner:
                project_owner_map[p.name] = p.owner
        for report in self.reports.values():
            for item in report.items:
                proj = item.project or "未分类"
                owner = project_owner_map.get(proj, "未分配负责人")
                if owner not in owner_groups:
                    owner_groups[owner] = {}
                if proj not in owner_groups[owner]:
                    owner_groups[owner][proj] = []
                owner_groups[owner][proj].append(item)
        if "未分类" not in project_owner_map:
            unassigned_projects = set()
            for report in self.reports.values():
                for item in report.items:
                    if not item.project or item.project not in project_owner_map:
                        unassigned_projects.add(item.project or "未分类")
            if unassigned_projects:
                owner = "未分配负责人"
                if owner not in owner_groups:
                    owner_groups[owner] = {}
                for proj in unassigned_projects:
                    if proj not in owner_groups[owner]:
                        owner_groups[owner][proj] = []
                    for report in self.reports.values():
                        for item in report.items:
                            if (item.project or "未分类") == proj:
                                owner_groups[owner][proj].append(item)
        return owner_groups
