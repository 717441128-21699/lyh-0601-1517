from datetime import datetime, timedelta
from typing import Optional
import click
import os
import sys

from .models import (
    TeamConfig, TeamSummary, WeeklyReport, Member, Project,
    ItemType, ItemStatus
)
from .storage import StorageManager
from .parser import parse_text_report, parse_excel_report


def _get_default_week() -> str:
    today = datetime.now()
    start = today - timedelta(days=today.weekday())
    return start.strftime("%Y-%m-%d")


def _require_init(storage: StorageManager) -> Optional[TeamConfig]:
    config = storage.load_config()
    if config is None:
        click.echo(click.style("错误：项目未初始化，请先运行 init 命令", fg="red"))
        return None
    return config


@click.group()
@click.version_option(version="1.0.0", prog_name="weekly-report")
def cli():
    """团队周报汇总工具 - 快速整理多成员进展"""
    pass


@cli.command()
@click.option("--team-name", prompt="请输入团队名称", help="团队名称")
@click.option("--members", help="团队成员列表，用逗号分隔")
@click.option("--projects", help="项目列表，用逗号分隔")
def init(team_name: str, members: Optional[str], projects: Optional[str]):
    """初始化项目配置，设置团队成员和项目列表"""
    storage = StorageManager()
    if storage.is_initialized():
        if not click.confirm("检测到已有配置，是否覆盖？"):
            click.echo("已取消初始化")
            return

    team_members = []
    if members:
        for name in members.split(","):
            name = name.strip()
            if name:
                team_members.append(Member(name=name))
    else:
        click.echo("请逐个输入团队成员（留空结束）：")
        idx = 1
        while True:
            name = click.prompt(f"  成员 {idx} 姓名", default="", show_default=False)
            if not name:
                break
            role = click.prompt(f"  成员 {idx} 角色（可选）", default="", show_default=False)
            email = click.prompt(f"  成员 {idx} 邮箱（可选）", default="", show_default=False)
            team_members.append(Member(name=name, role=role, email=email))
            idx += 1

    team_projects = []
    if projects:
        for name in projects.split(","):
            name = name.strip()
            if name:
                team_projects.append(Project(name=name))
    else:
        click.echo("请逐个输入项目名称（留空结束）：")
        idx = 1
        while True:
            name = click.prompt(f"  项目 {idx} 名称", default="", show_default=False)
            if not name:
                break
            owner = click.prompt(f"  项目 {idx} 负责人（可选）", default="", show_default=False)
            team_projects.append(Project(name=name, owner=owner))
            idx += 1

    config = TeamConfig(
        team_name=team_name,
        members=team_members,
        projects=team_projects
    )
    storage.save_config(config)
    click.echo(click.style(f"\n✓ 团队「{team_name}」初始化成功！", fg="green"))
    click.echo(f"  成员数：{len(team_members)}，项目数：{len(team_projects)}")


@cli.command()
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("--week", default=None, help="周起始日期 (YYYY-MM-DD)，默认本周一")
@click.option("--dir", "import_dir", default=None, help="批量导入目录下的所有文件")
@click.option("--format", "fmt", default="auto",
              type=click.Choice(["auto", "text", "excel"]),
              help="文件格式")
def import_cmd(files, week: Optional[str], import_dir: Optional[str], fmt: str):
    """导入成员周报，支持文本和表格格式"""
    storage = StorageManager()
    config = _require_init(storage)
    if config is None:
        return

    week_start = week or _get_default_week()
    click.echo(f"导入周期：{week_start} ~ {(datetime.strptime(week_start, '%Y-%m-%d') + timedelta(days=6)).strftime('%Y-%m-%d')}\n")

    all_files = list(files)
    if import_dir and os.path.isdir(import_dir):
        for fname in os.listdir(import_dir):
            fpath = os.path.join(import_dir, fname)
            if os.path.isfile(fpath):
                all_files.append(fpath)

    if not all_files:
        click.echo(click.style("错误：未指定任何文件", fg="red"))
        return

    known_projects = config.project_names()
    success_count = 0
    fail_count = 0

    for filepath in all_files:
        try:
            ext = os.path.splitext(filepath)[1].lower()
            file_fmt = fmt
            if file_fmt == "auto":
                if ext in [".xlsx", ".xls", ".csv"]:
                    file_fmt = "excel"
                else:
                    file_fmt = "text"

            reports = []
            if file_fmt == "excel":
                reports = parse_excel_report(
                    filepath,
                    known_projects=known_projects,
                    default_week_start=week_start
                )
            else:
                with open(filepath, "r", encoding="utf-8") as f:
                    text = f.read()
                report = parse_text_report(
                    text,
                    filename=filepath,
                    known_projects=known_projects,
                    default_week_start=week_start
                )
                report.week_start = week_start
                report.week_end = (datetime.strptime(week_start, "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d")
                reports = [report]

            for report in reports:
                if not report.week_start:
                    report.week_start = week_start
                if not report.week_end:
                    report.week_end = (datetime.strptime(report.week_start, "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d")

                storage.save_report(report)
                item_count = len(report.items)
                delayed = len(report.get_delayed_items())
                blocked = len(report.get_blocked_items())

                status_str = click.style("✓", fg="green")
                extra = ""
                if delayed:
                    extra += click.style(f" 延期:{delayed}", fg="yellow")
                if blocked:
                    extra += click.style(f" 阻塞:{blocked}", fg="red")

                click.echo(f"{status_str} {report.member_name} ({item_count}项){extra}")
                success_count += 1

        except Exception as e:
            fail_count += 1
            click.echo(click.style(f"✗ {os.path.basename(filepath)}: {e}", fg="red"))

    click.echo(f"\n完成：成功 {success_count} 份，失败 {fail_count} 份")


@cli.command()
@click.option("--week", default=None, help="周起始日期 (YYYY-MM-DD)")
def check(week: Optional[str]):
    """校验缺交人员，识别延期事项和阻塞问题"""
    storage = StorageManager()
    config = _require_init(storage)
    if config is None:
        return

    week_start = week or _get_default_week()
    week_end = (datetime.strptime(week_start, "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d")
    click.echo(click.style(f"\n=== 周报检查 ({week_start} ~ {week_end}) ===\n", fg="cyan", bold=True))

    reports = storage.load_all_reports_for_week(week_start)
    submitted_names = list(reports.keys())
    expected_names = config.member_names()

    missing = [m for m in expected_names if m not in submitted_names]
    unexpected = [m for m in submitted_names if m not in expected_names]

    click.echo(click.style(f"【提交情况】", fg="blue", bold=True))
    click.echo(f"  应交：{len(expected_names)} 人，已交：{len(submitted_names)} 人")
    if missing:
        click.echo(click.style(f"  缺交 ({len(missing)}人): {', '.join(missing)}", fg="red"))
    else:
        click.echo(click.style("  ✓ 全员已提交", fg="green"))
    if unexpected:
        click.echo(click.style(f"  额外提交: {', '.join(unexpected)}", fg="yellow"))

    all_delayed = []
    all_blocked = []
    all_help = []

    for member_name, report in reports.items():
        for item in report.items:
            if item.status == ItemStatus.DELAYED:
                all_delayed.append((member_name, item))
            if item.status == ItemStatus.BLOCKED:
                all_blocked.append((member_name, item))
            if item.item_type == ItemType.HELP:
                all_help.append((member_name, item))

    if all_delayed:
        click.echo(click.style(f"\n【延期事项】({len(all_delayed)}项)", fg="yellow", bold=True))
        for name, item in all_delayed:
            proj = f"[{item.project}]" if item.project else ""
            reason = f"（原因：{item.delay_reason}）" if item.delay_reason else ""
            click.echo(f"  • {name}: {proj} {item.content}{reason}")

    if all_blocked:
        click.echo(click.style(f"\n【阻塞事项】({len(all_blocked)}项)", fg="red", bold=True))
        for name, item in all_blocked:
            proj = f"[{item.project}]" if item.project else ""
            click.echo(f"  • {name}: {proj} {item.content}")

    if all_help:
        click.echo(click.style(f"\n【求助需求】({len(all_help)}项)", fg="magenta", bold=True))
        for name, item in all_help:
            proj = f"[{item.project}]" if item.project else ""
            click.echo(f"  • {name}: {proj} {item.content}")

    summary = TeamSummary(
        week_start=week_start,
        week_end=week_end,
        reports=reports,
        missing_members=missing,
    )
    follow_up = set(missing)
    for name, _ in all_delayed + all_blocked + all_help:
        follow_up.add(name)
    summary.follow_up_members = sorted(list(follow_up))
    storage.save_summary(summary)

    if summary.follow_up_members:
        click.echo(click.style(f"\n【需要跟进】({len(summary.follow_up_members)}人)", fg="red", bold=True))
        click.echo(f"  {', '.join(summary.follow_up_members)}")

    click.echo()


@cli.command()
@click.option("--week", default=None, help="周起始日期 (YYYY-MM-DD)")
@click.option("--group-by", default="project",
              type=click.Choice(["project", "member"]),
              help="按项目或成员归类显示")
@click.option("--add-note", is_flag=True, help="追加人工说明")
def summary(week: Optional[str], group_by: str, add_note: bool):
    """生成团队摘要，按项目/负责人归类，支持追加人工说明"""
    storage = StorageManager()
    config = _require_init(storage)
    if config is None:
        return

    week_start = week or _get_default_week()
    summary_data = storage.load_summary(week_start)

    if summary_data is None:
        reports = storage.load_all_reports_for_week(week_start)
        if not reports:
            click.echo(click.style("错误：暂无周报数据，请先运行 import 或 check 命令", fg="red"))
            return
        week_end = (datetime.strptime(week_start, "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d")
        summary_data = TeamSummary(
            week_start=week_start,
            week_end=week_end,
            reports=reports
        )

    if add_note:
        click.echo("请输入人工说明（输入空行结束）：")
        lines = []
        while True:
            line = input()
            if not line.strip():
                break
            lines.append(line)
        note_text = "\n".join(lines)
        if note_text.strip():
            if summary_data.manual_notes:
                summary_data.manual_notes += "\n\n" + note_text
            else:
                summary_data.manual_notes = note_text
            storage.save_summary(summary_data)
            click.echo(click.style("✓ 人工说明已追加", fg="green"))

    click.echo(click.style(
        f"\n{'='*60}\n  {config.team_name} 周报摘要 ({summary_data.week_start} ~ {summary_data.week_end})\n{'='*60}",
        fg="cyan", bold=True
    ))

    if summary_data.missing_members:
        click.echo(click.style(
            f"\n⚠ 缺交: {', '.join(summary_data.missing_members)}",
            fg="red"
        ))

    if summary_data.manual_notes:
        click.echo(click.style("\n【负责人说明】", fg="blue", bold=True))
        click.echo(f"  {summary_data.manual_notes}")

    total_completed = len(summary_data.get_all_items_by_type(ItemType.COMPLETED))
    total_planned = len(summary_data.get_all_items_by_type(ItemType.PLANNED))
    total_delayed = len(summary_data.get_all_delayed_items())
    total_blocked = len(summary_data.get_all_blocked_items())
    total_help = len(summary_data.get_all_items_by_type(ItemType.HELP))

    click.echo(click.style("\n【总体统计】", fg="blue", bold=True))
    click.echo(f"  本周完成: {total_completed} | 下周计划: {total_planned} | 延期: {total_delayed} | 阻塞: {total_blocked} | 求助: {total_help}")

    if group_by == "project":
        groups = summary_data.group_items_by_project()
        click.echo(click.style("\n【按项目分类】", fg="blue", bold=True))
        for proj_name in sorted(groups.keys()):
            items = groups[proj_name]
            completed = [i for i in items if i.item_type == ItemType.COMPLETED]
            planned = [i for i in items if i.item_type == ItemType.PLANNED]
            risks = [i for i in items if i.item_type == ItemType.RISK]
            helps = [i for i in items if i.item_type == ItemType.HELP]

            click.echo(click.style(f"\n▸ {proj_name}", fg="green", bold=True))
            for title, item_list in [
                ("完成", completed), ("计划", planned), ("风险", risks), ("求助", helps)
            ]:
                if item_list:
                    color = {"完成": "green", "计划": "blue", "风险": "yellow", "求助": "magenta"}[title]
                    click.echo(click.style(f"  {title}({len(item_list)}):", fg=color, bold=True))
                    for it in item_list:
                        tag = ""
                        if it.status == ItemStatus.DELAYED:
                            tag = click.style(" [延期]", fg="yellow")
                        elif it.status == ItemStatus.BLOCKED:
                            tag = click.style(" [阻塞]", fg="red")
                        click.echo(f"    - {it.assignee}: {it.content}{tag}")
    else:
        groups = summary_data.group_items_by_member_and_type()
        click.echo(click.style("\n【按成员分类】", fg="blue", bold=True))
        for member_name in sorted(groups.keys()):
            type_groups = groups[member_name]
            click.echo(click.style(f"\n▸ {member_name}", fg="green", bold=True))
            for itype, title in [
                (ItemType.COMPLETED, "本周完成"),
                (ItemType.PLANNED, "下周计划"),
                (ItemType.RISK, "风险阻塞"),
                (ItemType.HELP, "求助需求")
            ]:
                items = type_groups.get(itype, [])
                if items:
                    color = {
                        ItemType.COMPLETED: "green",
                        ItemType.PLANNED: "blue",
                        ItemType.RISK: "yellow",
                        ItemType.HELP: "magenta"
                    }[itype]
                    click.echo(click.style(f"  {title}({len(items)}):", fg=color, bold=True))
                    for it in items:
                        proj = f"[{it.project}] " if it.project else ""
                        tag = ""
                        if it.status == ItemStatus.DELAYED:
                            tag = click.style(" [延期]", fg="yellow")
                        elif it.status == ItemStatus.BLOCKED:
                            tag = click.style(" [阻塞]", fg="red")
                        click.echo(f"    - {proj}{it.content}{tag}")

    if summary_data.follow_up_members:
        click.echo(click.style(f"\n【需要跟进人员】", fg="red", bold=True))
        click.echo(f"  {', '.join(summary_data.follow_up_members)}")

    click.echo()


@cli.command()
@click.option("--week", default=None, help="周起始日期 (YYYY-MM-DD)")
@click.option("--format", "fmt", default="email",
              type=click.Choice(["email", "group", "both"]),
              help="导出格式：email(邮件格式) / group(群公告格式) / both")
@click.option("--output", default=None, help="输出文件名（不含扩展名）")
def export(week: Optional[str], fmt: str, output: Optional[str]):
    """导出周报，支持邮件格式和群公告格式"""
    storage = StorageManager()
    config = _require_init(storage)
    if config is None:
        return

    week_start = week or _get_default_week()
    summary_data = storage.load_summary(week_start)

    if summary_data is None:
        reports = storage.load_all_reports_for_week(week_start)
        if not reports:
            click.echo(click.style("错误：暂无周报数据，请先运行 summary 命令", fg="red"))
            return
        week_end = (datetime.strptime(week_start, "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d")
        summary_data = TeamSummary(
            week_start=week_start,
            week_end=week_end,
            reports=reports
        )

    base_name = output or f"{config.team_name}周报"

    if fmt in ["email", "both"]:
        content = _format_email(config, summary_data)
        path = storage.get_export_path(week_start, f"{base_name}_邮件.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        click.echo(click.style(f"✓ 邮件格式已导出: {path}", fg="green"))

    if fmt in ["group", "both"]:
        content = _format_group(config, summary_data)
        path = storage.get_export_path(week_start, f"{base_name}_群公告.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        click.echo(click.style(f"✓ 群公告格式已导出: {path}", fg="green"))


def _format_email(config: TeamConfig, s: TeamSummary) -> str:
    lines = []
    lines.append(f"【主题】{config.team_name}周报 ({s.week_start} ~ {s.week_end})")
    lines.append("=" * 60)
    lines.append("")

    if s.manual_notes:
        lines.append("【负责人说明】")
        lines.append(s.manual_notes)
        lines.append("")

    header_info = f"提交情况：{len(s.reports)}/{len(config.members)} 人"
    if s.missing_members:
        header_info += f"（缺交：{', '.join(s.missing_members)}）"
    lines.append(header_info)
    lines.append("")

    completed = s.get_all_items_by_type(ItemType.COMPLETED)
    planned = s.get_all_items_by_type(ItemType.PLANNED)
    delayed = s.get_all_delayed_items()
    blocked = s.get_all_blocked_items()
    helps = s.get_all_items_by_type(ItemType.HELP)

    lines.append(f"【本周亮点】完成 {len(completed)} 项，计划 {len(planned)} 项")
    if delayed or blocked:
        lines.append(f"【风险预警】延期 {len(delayed)} 项，阻塞 {len(blocked)} 项")
    if helps:
        lines.append(f"【求助需求】{len(helps)} 项")
    lines.append("")

    lines.append("=" * 60)
    lines.append("一、本周完成情况")
    lines.append("=" * 60)
    by_project = s.group_items_by_project()
    for proj_name in sorted(by_project.keys()):
        proj_items = by_project[proj_name]
        proj_completed = [i for i in proj_items if i.item_type == ItemType.COMPLETED]
        if proj_completed:
            lines.append(f"\n【{proj_name}】")
            for it in proj_completed:
                tag = " [延期]" if it.status == ItemStatus.DELAYED else ""
                lines.append(f"  - {it.assignee}: {it.content}{tag}")

    lines.append("")
    lines.append("=" * 60)
    lines.append("二、下周工作计划")
    lines.append("=" * 60)
    for proj_name in sorted(by_project.keys()):
        proj_items = by_project[proj_name]
        proj_planned = [i for i in proj_items if i.item_type == ItemType.PLANNED]
        if proj_planned:
            lines.append(f"\n【{proj_name}】")
            for it in proj_planned:
                deadline = f"（截止：{it.deadline}）" if it.deadline else ""
                lines.append(f"  - {it.assignee}: {it.content}{deadline}")

    if delayed or blocked:
        lines.append("")
        lines.append("=" * 60)
        lines.append("三、风险与阻塞")
        lines.append("=" * 60)
        if delayed:
            lines.append("\n【延期事项】")
            for name, report in s.reports.items():
                for it in report.get_delayed_items():
                    proj = f"[{it.project}] " if it.project else ""
                    reason = f"（原因：{it.delay_reason}）" if it.delay_reason else ""
                    lines.append(f"  - {name}: {proj}{it.content}{reason}")
        if blocked:
            lines.append("\n【阻塞事项】")
            for name, report in s.reports.items():
                for it in report.get_blocked_items():
                    proj = f"[{it.project}] " if it.project else ""
                    lines.append(f"  - {name}: {proj}{it.content}")

    if helps:
        lines.append("")
        lines.append("=" * 60)
        lines.append("四、求助与支持需求")
        lines.append("=" * 60)
        for it in helps:
            proj = f"[{it.project}] " if it.project else ""
            lines.append(f"  - {it.assignee}: {proj}{it.content}")

    if s.follow_up_members:
        lines.append("")
        lines.append("=" * 60)
        lines.append("五、需要跟进的人员")
        lines.append("=" * 60)
        lines.append(f"  {', '.join(s.follow_up_members)}")

    lines.append("")
    lines.append("-" * 60)
    lines.append(f"本报表由团队周报汇总工具自动生成")
    return "\n".join(lines)


def _format_group(config: TeamConfig, s: TeamSummary) -> str:
    lines = []
    lines.append(f"📢 {config.team_name}周报速报")
    lines.append(f"📅 {s.week_start} ~ {s.week_end}")
    lines.append("")

    total = len(config.members)
    submitted = len(s.reports)
    lines.append(f"✅ 周报提交：{submitted}/{total} 人")
    if s.missing_members:
        lines.append(f"❌ 缺交人员：{', '.join(s.missing_members)}")
    lines.append("")

    completed = s.get_all_items_by_type(ItemType.COMPLETED)
    planned = s.get_all_items_by_type(ItemType.PLANNED)
    delayed = s.get_all_delayed_items()
    blocked = s.get_all_blocked_items()
    helps = s.get_all_items_by_type(ItemType.HELP)

    lines.append(f"📊 本周概览：")
    lines.append(f"  • 完成事项：{len(completed)} 项")
    lines.append(f"  • 下周计划：{len(planned)} 项")
    if delayed:
        lines.append(f"  ⚠️  延期事项：{len(delayed)} 项")
    if blocked:
        lines.append(f"  🚫 阻塞事项：{len(blocked)} 项")
    if helps:
        lines.append(f"  🆘 求助需求：{len(helps)} 项")
    lines.append("")

    if s.manual_notes:
        lines.append("💬 负责人备注：")
        for line in s.manual_notes.split('\n'):
            lines.append(f"  {line}")
        lines.append("")

    if delayed or blocked or helps:
        lines.append("🔴 重点关注：")
        if delayed:
            lines.append("  【延期】")
            for name, report in s.reports.items():
                for it in report.get_delayed_items():
                    lines.append(f"    - {name}: {it.content[:30]}{'...' if len(it.content) > 30 else ''}")
        if blocked:
            lines.append("  【阻塞】")
            for name, report in s.reports.items():
                for it in report.get_blocked_items():
                    lines.append(f"    - {name}: {it.content[:30]}{'...' if len(it.content) > 30 else ''}")
        if helps:
            lines.append("  【求助】")
            for it in helps:
                lines.append(f"    - {it.assignee}: {it.content[:30]}{'...' if len(it.content) > 30 else ''}")
        lines.append("")

    if s.follow_up_members:
        lines.append(f"👥 需要跟进：{', '.join(s.follow_up_members)}")
        lines.append("")

    lines.append("—— 详情见邮件 ——")
    return "\n".join(lines)


def main():
    cli()


if __name__ == "__main__":
    main()
