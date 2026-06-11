from datetime import datetime, timedelta
from typing import List, Optional
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


@click.group(
    help="""团队周报汇总工具 - 快速整理多成员进展

\b
常用流程：
  1. init     初始化团队和项目配置（首次使用）
  2. import   批量导入各成员周报
  3. check    校验缺交/延期/阻塞情况
  4. summary  生成汇总摘要，可追加负责人说明
  5. export   导出为邮件/群公告/Markdown格式
  6. history  查看周报历史版本
  7. rollback 回滚到指定历史版本
""",
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.version_option("1.1.0", "-v", "--version", prog_name="weekly-report")
def cli():
    """团队周报汇总工具 - 快速整理多成员进展"""
    pass


@cli.command("init", short_help="初始化项目（设置团队成员和项目）")
@click.option("--team-name", prompt="请输入团队名称", help="团队名称")
@click.option("--members", default=None,
              help="团队成员列表，用逗号分隔（如：张三,李四,王五）")
@click.option("--projects", default=None,
              help="项目名称列表，用逗号分隔（如：用户中心,订单系统）")
@click.option("-y", "--yes", is_flag=True,
              help="已有配置时直接覆盖，不询问")
def init_cmd(team_name: str, members: Optional[str], projects: Optional[str], yes: bool):
    """
    初始化项目配置，设置团队成员和项目列表。

    \b
    首次使用时必需执行。可以通过参数一次性配置：
      python main.py init --team-name 研发部 --members "张三,李四" --projects "用户中心,订单系统"

    \b
    也可以不带参数，进入交互式引导配置（支持填写角色、邮箱、项目负责人等）。

    已初始化后再次执行，会询问是否覆盖原有配置。
    """
    storage = StorageManager()
    if storage.is_initialized() and not yes:
        if not click.confirm("检测到已有配置，是否覆盖？", default=False):
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
    if team_members:
        click.echo(f"  成员：{', '.join(m.name for m in team_members)}")
    if team_projects:
        click.echo(f"  项目：{', '.join(p.name for p in team_projects)}")


@cli.command("import", short_help="导入成员周报（文本/Excel/目录批量）")
@click.argument("files", nargs=-1, type=click.Path(exists=True))
@click.option("-w", "--week", default=None,
              help="周起始日期 (YYYY-MM-DD)，默认本周一")
@click.option("-d", "--dir", "import_dir", default=None,
              type=click.Path(exists=True, file_okay=False),
              help="批量导入目录下的所有周报文件")
@click.option("-f", "--format", "fmt", default="auto",
              type=click.Choice(["auto", "text", "excel"]),
              help="文件格式，auto 自动根据扩展名识别")
@click.option("--on-duplicate", default="ask",
              type=click.Choice(["ask", "overwrite", "skip"]),
              help="同一成员同一周重复导入时的处理方式：ask(询问)/overwrite(覆盖)/skip(跳过)")
@click.option("--no-check", is_flag=True,
              help="导入后不自动执行 check")
def import_cmd(files, week: Optional[str], import_dir: Optional[str],
               fmt: str, on_duplicate: str, no_check: bool):
    """
    导入成员周报，支持文本 (.txt/.md)、Excel (.xlsx) 表格，以及目录批量导入。

    \b
    - 文本文件：按「本周完成/下周计划/风险阻塞/求助需求」自动解析
    - Excel：逐 sheet 解析，可在文件内直接写周报结构
    - 目录导入：自动识别目录下所有支持的文件

    同一成员同一周重复导入时，可选择覆盖或跳过，避免旧数据被悄悄覆盖。
    导入完成后默认自动执行 check，查看整体提交情况。
    """
    storage = StorageManager()
    config = _require_init(storage)
    if config is None:
        return

    week_start = week or _get_default_week()
    week_end = (datetime.strptime(week_start, "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d")
    click.echo(click.style(f"\n=== 导入周报 ({week_start} ~ {week_end}) ===", fg="cyan", bold=True))

    all_files = list(files)
    if import_dir and os.path.isdir(import_dir):
        for fname in sorted(os.listdir(import_dir)):
            fpath = os.path.join(import_dir, fname)
            if os.path.isfile(fpath):
                ext = os.path.splitext(fname)[1].lower()
                if ext in [".txt", ".md", ".xlsx", ".xls", ".csv"]:
                    all_files.append(fpath)
        click.echo(f"从目录发现 {len([f for f in all_files if f.startswith(import_dir)])} 个文件")

    if not all_files:
        click.echo(click.style("错误：未指定任何文件，请传入文件路径或使用 --dir 指定目录", fg="red"))
        return

    known_projects = config.project_names()
    success_count = 0
    fail_count = 0
    skip_count = 0
    overwrite_count = 0

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
                report.week_end = week_end
                reports = [report]

            for report in reports:
                if not report.week_start:
                    report.week_start = week_start
                if not report.week_end:
                    report.week_end = (datetime.strptime(report.week_start, "%Y-%m-%d")
                                       + timedelta(days=6)).strftime("%Y-%m-%d")

                is_dup = storage.has_report(report.week_start, report.member_name)
                action = on_duplicate
                if is_dup and action == "ask":
                    old_report = storage.load_report(report.week_start, report.member_name)
                    old_time = old_report.submitted_at if old_report else "未知时间"
                    click.echo()
                    click.echo(click.style(f"⚠ 检测到重复提交：{report.member_name}", fg="yellow"))
                    click.echo(f"  原提交时间：{old_time}，共 {len(old_report.items) if old_report else 0} 项")
                    click.echo(f"  新文件：{os.path.basename(filepath)}，共 {len(report.items)} 项")
                    if click.confirm("  是否覆盖旧数据？", default=False):
                        action = "overwrite"
                    else:
                        action = "skip"

                if is_dup and action == "skip":
                    click.echo(click.style(f"⊘ {report.member_name} 已存在，跳过", fg="yellow"))
                    skip_count += 1
                    continue

                storage.save_report(report)
                item_count = len(report.items)
                delayed = len(report.get_delayed_items())
                blocked = len(report.get_blocked_items())

                if is_dup and action == "overwrite":
                    storage.save_version(report.week_start, report.member_name)
                    status_str = click.style("↻", fg="yellow")
                    label = "覆盖"
                    overwrite_count += 1
                else:
                    status_str = click.style("✓", fg="green")
                    label = "新增"
                    success_count += 1

                extra = ""
                if delayed:
                    extra += click.style(f" 延期:{delayed}", fg="yellow")
                if blocked:
                    extra += click.style(f" 阻塞:{blocked}", fg="red")

                click.echo(f"{status_str} {report.member_name} [{label}] ({item_count}项){extra}")

        except Exception as e:
            fail_count += 1
            click.echo(click.style(f"✗ {os.path.basename(filepath)}: {e}", fg="red"))

    total = success_count + skip_count + overwrite_count
    click.echo()
    click.echo(click.style("导入完成：", fg="cyan", bold=True) +
               f"新增 {success_count} 份，覆盖 {overwrite_count} 份，跳过 {skip_count} 份，失败 {fail_count} 份")

    if (success_count + overwrite_count) > 0:
        summary_file = storage._get_summary_file(week_start)
        preserved_notes = ""
        if os.path.exists(summary_file):
            old_summary = storage.load_summary(week_start)
            if old_summary and old_summary.manual_notes:
                preserved_notes = old_summary.manual_notes
            os.remove(summary_file)

        if preserved_notes:
            reports = storage.load_all_reports_for_week(week_start)
            week_end_val = (datetime.strptime(week_start, "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d")
            new_summary = TeamSummary(
                week_start=week_start,
                week_end=week_end_val,
                reports=reports,
                manual_notes=preserved_notes
            )
            storage.save_summary(new_summary)

    if not no_check and (success_count + overwrite_count) > 0:
        click.echo()
        _run_check(storage, config, week_start)


@cli.command(short_help="校验周报（缺交/延期/阻塞/求助统计）")
@click.option("-w", "--week", default=None,
              help="周起始日期 (YYYY-MM-DD)，默认本周一")
@click.option("--save", is_flag=True, default=True,
              help="保存校验结果为摘要，供后续 summary / export 使用")
def check(week: Optional[str], save: bool):
    """
    校验本周周报提交情况，识别风险项。

    \b
    输出内容：
    - 提交情况：应交/已交/缺交人员名单
    - 延期事项：带原因
    - 阻塞事项：需要推动的卡点
    - 求助需求：等待他人支持的事项
    - 需要跟进：汇总所有需要关注的人员
    """
    storage = StorageManager()
    config = _require_init(storage)
    if config is None:
        return

    week_start = week or _get_default_week()
    _run_check(storage, config, week_start, save=save)


def _run_check(storage: StorageManager, config: TeamConfig,
               week_start: str, save: bool = True) -> TeamSummary:
    """执行周报检查并返回 TeamSummary，可由其他命令复用"""
    week_end = (datetime.strptime(week_start, "%Y-%m-%d") + timedelta(days=6)).strftime("%Y-%m-%d")
    click.echo(click.style(f"=== 周报检查 ({week_start} ~ {week_end}) ===", fg="cyan", bold=True))

    reports = storage.load_all_reports_for_week(week_start)
    submitted_names = list(reports.keys())
    expected_names = config.member_names()

    missing = [m for m in expected_names if m not in submitted_names]
    unexpected = [m for m in submitted_names if m not in expected_names]

    click.echo()
    click.echo(click.style("【提交情况】", fg="blue", bold=True))
    click.echo(f"  应交：{len(expected_names)} 人，已交：{len(submitted_names)} 人")
    if missing:
        click.echo(click.style(f"  缺交 ({len(missing)}人): {', '.join(missing)}", fg="red"))
    else:
        click.echo(click.style("  ✓ 全员已提交", fg="green"))
    if unexpected:
        click.echo(click.style(f"  额外提交(不在名册): {', '.join(unexpected)}", fg="yellow"))

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

    old_summary = storage.load_summary(week_start)
    if old_summary and old_summary.manual_notes:
        summary.manual_notes = old_summary.manual_notes

    if save:
        storage.save_summary(summary)

    if summary.follow_up_members:
        click.echo(click.style(f"\n【需要跟进】({len(summary.follow_up_members)}人)", fg="red", bold=True))
        click.echo(f"  {', '.join(summary.follow_up_members)}")

    click.echo()
    return summary


@cli.command(short_help="生成团队摘要（按项目/成员/负责人/风险归类）")
@click.option("-w", "--week", default=None,
              help="周起始日期 (YYYY-MM-DD)，默认本周一")
@click.option("-g", "--group-by", default="project",
              type=click.Choice(["project", "member", "owner", "risk"]),
              help="归类维度：project(按项目) / member(按成员) / owner(按项目负责人) / risk(按风险等级)")
@click.option("--add-note", is_flag=True,
              help="追加人工说明到摘要中（供导出使用）")
@click.option("--brief", is_flag=True,
              help="只显示总体统计和重点关注，不展开所有条目")
def summary(week: Optional[str], group_by: str, add_note: bool, brief: bool):
    """
    生成团队周报摘要，支持四种归类视角，可追加负责人人工说明。

    \b
    归类维度：
    - project：按项目归类（默认），适合项目负责人看整体进展
    - member：按成员归类，适合逐个了解成员工作
    - owner：按项目负责人归类，负责人能直接看到自己名下所有项目的进展、风险和求助
    - risk：按风险等级归类，把延期、阻塞、求助按负责人和成员列出，一眼看到谁需要跟进

    追加的人工说明会在导出邮件/群公告/Markdown时，放在开头显眼位置。
    """
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
            f"\n⚠ 缺交 ({len(summary_data.missing_members)}人): {', '.join(summary_data.missing_members)}",
            fg="red"
        ))

    if summary_data.manual_notes:
        click.echo(click.style("\n【负责人说明】", fg="blue", bold=True))
        for line in summary_data.manual_notes.split('\n'):
            click.echo(f"  {line}")

    total_completed = len(summary_data.get_all_items_by_type(ItemType.COMPLETED))
    total_planned = len(summary_data.get_all_items_by_type(ItemType.PLANNED))
    total_delayed = len(summary_data.get_all_delayed_items())
    total_blocked = len(summary_data.get_all_blocked_items())
    total_help = len(summary_data.get_all_items_by_type(ItemType.HELP))

    click.echo(click.style("\n【总体统计】", fg="blue", bold=True))
    click.echo(f"  本周完成: {total_completed} | 下周计划: {total_planned} | "
               f"延期: {total_delayed} | 阻塞: {total_blocked} | 求助: {total_help}")

    if brief:
        _print_brief_focus(summary_data)
        click.echo()
        return

    if group_by == "project":
        _print_summary_by_project(summary_data)
    elif group_by == "member":
        _print_summary_by_member(summary_data)
    elif group_by == "owner":
        _print_summary_by_owner(summary_data, config.projects)
    elif group_by == "risk":
        _print_summary_by_risk(summary_data, config.projects)

    if summary_data.follow_up_members:
        click.echo(click.style(f"\n【需要跟进人员】", fg="red", bold=True))
        click.echo(f"  {', '.join(summary_data.follow_up_members)}")

    click.echo()


def _print_brief_focus(summary_data: TeamSummary):
    delayed = summary_data.get_all_delayed_items()
    blocked = summary_data.get_all_blocked_items()
    helps = summary_data.get_all_items_by_type(ItemType.HELP)

    if delayed or blocked or helps:
        click.echo(click.style("\n【重点关注】", fg="red", bold=True))
        if delayed:
            click.echo(f"  延期 {len(delayed)} 项")
        if blocked:
            click.echo(f"  阻塞 {len(blocked)} 项")
        if helps:
            click.echo(f"  求助 {len(helps)} 项")


def _print_summary_by_project(summary_data: TeamSummary):
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


def _print_summary_by_member(summary_data: TeamSummary):
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


def _print_summary_by_owner(summary_data: TeamSummary, projects: List[Project]):
    owner_groups = summary_data.group_items_by_owner(projects)
    click.echo(click.style("\n【按项目负责人分类】", fg="blue", bold=True))
    for owner_name in sorted(owner_groups.keys()):
        proj_items = owner_groups[owner_name]
        all_items = []
        for items in proj_items.values():
            all_items.extend(items)
        completed = [i for i in all_items if i.item_type == ItemType.COMPLETED]
        planned = [i for i in all_items if i.item_type == ItemType.PLANNED]
        risks = [i for i in all_items if i.item_type == ItemType.RISK]
        helps = [i for i in all_items if i.item_type == ItemType.HELP]
        delayed = [i for i in all_items if i.status == ItemStatus.DELAYED]
        blocked = [i for i in all_items if i.status == ItemStatus.BLOCKED]

        proj_count = len(proj_items)
        click.echo(click.style(f"\n▸ {owner_name} ({proj_count}个项目)", fg="green", bold=True))
        click.echo(f"  完成:{len(completed)} 计划:{len(planned)} "
                   f"风险:{len(risks)} 求助:{len(helps)} "
                   f"延期:{len(delayed)} 阻塞:{len(blocked)}")

        for proj_name in sorted(proj_items.keys()):
            items = proj_items[proj_name]
            proj_risks = [i for i in items if i.item_type == ItemType.RISK]
            proj_helps = [i for i in items if i.item_type == ItemType.HELP]
            proj_delayed = [i for i in items if i.status == ItemStatus.DELAYED]
            proj_blocked = [i for i in items if i.status == ItemStatus.BLOCKED]

            if proj_risks or proj_helps or proj_delayed or proj_blocked:
                click.echo(click.style(f"  【{proj_name}】重点：", fg="yellow"))
                for it in proj_risks:
                    tag = ""
                    if it.status == ItemStatus.DELAYED:
                        tag = " [延期]"
                    elif it.status == ItemStatus.BLOCKED:
                        tag = " [阻塞]"
                    click.echo(f"    ⚠ {it.assignee}: {it.content}{tag}")
                for it in proj_helps:
                    click.echo(f"    🆘 {it.assignee}: {it.content}")
            else:
                click.echo(f"  【{proj_name}】进展顺利")


def _print_summary_by_risk(summary_data: TeamSummary, projects: List[Project]):
    risk_groups = summary_data.group_items_by_risk(projects)
    click.echo(click.style("\n【按风险等级分类】", fg="red", bold=True))

    if not risk_groups:
        click.echo(click.style("  ✓ 本周无延期、阻塞或求助事项", fg="green"))
        return

    cat_config = {
        "阻塞": {"icon": "🚫", "color": "red"},
        "延期": {"icon": "⚠️", "color": "yellow"},
        "求助": {"icon": "🆘", "color": "magenta"},
    }

    for cat_name in ["阻塞", "延期", "求助"]:
        if cat_name not in risk_groups:
            continue
        cfg = cat_config[cat_name]
        cat_items = risk_groups[cat_name]
        total_count = sum(len(items) for items in cat_items.values())
        click.echo(click.style(
            f"\n  {cfg['icon']} {cat_name} ({total_count}项)", fg=cfg["color"], bold=True
        ))
        for key in sorted(cat_items.keys()):
            items = cat_items[key]
            click.echo(click.style(f"    [{key}] ({len(items)}项)", fg="cyan"))
            for it in items:
                proj = f"[{it.project}] " if it.project else ""
                reason = f"（原因：{it.delay_reason}）" if it.delay_reason else ""
                click.echo(f"      - {proj}{it.content}{reason}")

    all_risk_members = set()
    for cat_items in risk_groups.values():
        for key in cat_items.keys():
            parts = key.split(" / ")
            if len(parts) >= 2:
                all_risk_members.add(parts[-1])
    if all_risk_members:
        click.echo(click.style(f"\n  需重点跟进人员：{', '.join(sorted(all_risk_members))}", fg="red", bold=True))


@cli.command(short_help="导出周报（邮件/群公告/Markdown）")
@click.option("-w", "--week", default=None,
              help="周起始日期 (YYYY-MM-DD)，默认本周一")
@click.option("-f", "--format", "fmt", default="email",
              type=click.Choice(["email", "group", "markdown", "all"]),
              help="导出格式：email(邮件) / group(群公告) / markdown / all(全部)")
@click.option("-o", "--output-dir", "output_dir", default=None,
              type=click.Path(file_okay=False),
              help="输出目录，默认 weekly_exports/")
@click.option("--filename", default=None,
              help="自定义文件名前缀（不含扩展名和日期）")
def export(week: Optional[str], fmt: str, output_dir: Optional[str], filename: Optional[str]):
    """
    导出周报，支持邮件格式、群公告格式和 Markdown 格式。

    \b
    输出内容统一包含：
    - 负责人说明（如有）
    - 缺交人员名单
    - 本周完成 / 下周计划
    - 风险阻塞 / 求助需求
    - 需要跟进的人员

    文件名自动包含团队名和周起止日期，便于归档管理。
    """
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

    if output_dir:
        storage.export_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    base_name = filename or f"{config.team_name}周报"
    week_tag = f"{summary_data.week_start}_{summary_data.week_end}"

    if fmt in ["email", "all"]:
        content = _format_email(config, summary_data)
        path = os.path.join(storage.export_dir, f"{base_name}_邮件版_{week_tag}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        click.echo(click.style(f"✓ 邮件格式已导出: {path}", fg="green"))

    if fmt in ["group", "all"]:
        content = _format_group(config, summary_data)
        path = os.path.join(storage.export_dir, f"{base_name}_群公告版_{week_tag}.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        click.echo(click.style(f"✓ 群公告格式已导出: {path}", fg="green"))

    if fmt in ["markdown", "all"]:
        content = _format_markdown(config, summary_data)
        path = os.path.join(storage.export_dir, f"{base_name}_{week_tag}.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        click.echo(click.style(f"✓ Markdown 格式已导出: {path}", fg="green"))


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
    lines.append(f"本报表由团队周报汇总工具自动生成  |  {s.week_start} ~ {s.week_end}")
    return "\n".join(lines)


def _format_group(config: TeamConfig, s: TeamSummary) -> str:
    lines = []
    lines.append(f"📢 {config.team_name}周报速报")
    lines.append(f"📅 {s.week_start} ~ {s.week_end}")
    lines.append("")

    if s.manual_notes:
        lines.append("💬 负责人备注：")
        for line in s.manual_notes.split('\n'):
            lines.append(f"  {line}")
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

    if delayed or blocked or helps:
        lines.append("🔴 重点关注：")
        if delayed:
            lines.append("  【延期】")
            for name, report in s.reports.items():
                for it in report.get_delayed_items():
                    short = it.content[:30] + "..." if len(it.content) > 30 else it.content
                    lines.append(f"    - {name}: {short}")
        if blocked:
            lines.append("  【阻塞】")
            for name, report in s.reports.items():
                for it in report.get_blocked_items():
                    short = it.content[:30] + "..." if len(it.content) > 30 else it.content
                    lines.append(f"    - {name}: {short}")
        if helps:
            lines.append("  【求助】")
            for it in helps:
                short = it.content[:30] + "..." if len(it.content) > 30 else it.content
                lines.append(f"    - {it.assignee}: {short}")
        lines.append("")

    if s.follow_up_members:
        lines.append(f"👥 需要跟进：{', '.join(s.follow_up_members)}")
        lines.append("")

    lines.append("—— 详情见邮件 ——")
    return "\n".join(lines)


def _format_markdown(config: TeamConfig, s: TeamSummary) -> str:
    lines = []
    lines.append(f"# {config.team_name}周报")
    lines.append("")
    lines.append(f"> **周期**：{s.week_start} ~ {s.week_end}  ")
    lines.append(f"> **提交**：{len(s.reports)}/{len(config.members)} 人"
                 + (f"  |  **缺交**：{', '.join(s.missing_members)}" if s.missing_members else ""))
    if s.follow_up_members:
        lines.append(f"> **需要跟进**：{', '.join(s.follow_up_members)}")
    lines.append("")

    if s.manual_notes:
        lines.append("## � 负责人说明")
        lines.append("")
        for line in s.manual_notes.split('\n'):
            lines.append(f"> {line}" if line.strip() else ">")
        lines.append("")

    completed = s.get_all_items_by_type(ItemType.COMPLETED)
    planned = s.get_all_items_by_type(ItemType.PLANNED)
    delayed = s.get_all_delayed_items()
    blocked = s.get_all_blocked_items()
    helps = s.get_all_items_by_type(ItemType.HELP)

    lines.append("## 📊 数据概览")
    lines.append("")
    lines.append("| 类别 | 数量 |")
    lines.append("|------|------|")
    lines.append(f"| 本周完成 | {len(completed)} |")
    lines.append(f"| 下周计划 | {len(planned)} |")
    lines.append(f"| 延期事项 | {len(delayed)} |")
    lines.append(f"| 阻塞事项 | {len(blocked)} |")
    lines.append(f"| 求助需求 | {len(helps)} |")
    lines.append("")

    by_project = s.group_items_by_project()

    lines.append("## ✅ 本周完成情况")
    lines.append("")
    for proj_name in sorted(by_project.keys()):
        proj_items = by_project[proj_name]
        proj_completed = [i for i in proj_items if i.item_type == ItemType.COMPLETED]
        if proj_completed:
            lines.append(f"### {proj_name}")
            lines.append("")
            for it in proj_completed:
                tag = " `延期` " if it.status == ItemStatus.DELAYED else " "
                lines.append(f"- {it.assignee}：{it.content}{tag}")
            lines.append("")

    lines.append("## 📅 下周工作计划")
    lines.append("")
    for proj_name in sorted(by_project.keys()):
        proj_items = by_project[proj_name]
        proj_planned = [i for i in proj_items if i.item_type == ItemType.PLANNED]
        if proj_planned:
            lines.append(f"### {proj_name}")
            lines.append("")
            for it in proj_planned:
                deadline = f" _截止：{it.deadline}_" if it.deadline else ""
                lines.append(f"- {it.assignee}：{it.content}{deadline}")
            lines.append("")

    if delayed or blocked:
        lines.append("## ⚠️ 风险与阻塞")
        lines.append("")
        if delayed:
            lines.append("### 延期事项")
            lines.append("")
            for name, report in s.reports.items():
                for it in report.get_delayed_items():
                    proj = f"**[{it.project}]** " if it.project else ""
                    reason = f"（原因：{it.delay_reason}）" if it.delay_reason else ""
                    lines.append(f"- **{name}**：{proj}{it.content} {reason}")
            lines.append("")
        if blocked:
            lines.append("### 阻塞事项")
            lines.append("")
            for name, report in s.reports.items():
                for it in report.get_blocked_items():
                    proj = f"**[{it.project}]** " if it.project else ""
                    lines.append(f"- **{name}**：{proj}{it.content}")
            lines.append("")

    if helps:
        lines.append("## 🆘 求助与支持需求")
        lines.append("")
        for it in helps:
            proj = f"**[{it.project}]** " if it.project else ""
            lines.append(f"- **{it.assignee}**：{proj}{it.content}")
        lines.append("")

    if s.follow_up_members:
        lines.append("## 👥 需要跟进的人员")
        lines.append("")
        lines.append(", ".join(f"**{m}**" for m in s.follow_up_members))
        lines.append("")

    lines.append("---")
    lines.append("")
    lines.append(f"_本报表由团队周报汇总工具自动生成  |  {s.week_start} ~ {s.week_end}_")
    return "\n".join(lines)


@cli.command("history", short_help="查看周报历史版本")
@click.option("-w", "--week", default=None,
              help="周起始日期 (YYYY-MM-DD)，默认本周一")
@click.option("-m", "--member", default=None,
              help="指定成员名称，不填则列出所有成员的版本")
def history_cmd(week: Optional[str], member: Optional[str]):
    """
    查看周报的历史版本记录。

    覆盖导入时会自动保存旧版本，通过此命令可以查看历史。
    配合 rollback 命令可以回滚到指定版本。

    \b
    用法：
      python main.py history -w 2026-06-08          # 查看所有成员的版本
      python main.py history -w 2026-06-08 -m 张三   # 只看张三的版本
    """
    storage = StorageManager()
    config = _require_init(storage)
    if config is None:
        return

    week_start = week or _get_default_week()
    click.echo(click.style(f"\n=== 历史版本 ({week_start}) ===", fg="cyan", bold=True))

    if member:
        members = [member]
    else:
        members = config.member_names()
        reports = storage.load_all_reports_for_week(week_start)
        for m in reports:
            if m not in members:
                members.append(m)

    found_any = False
    for m in members:
        versions = storage.list_versions(week_start, m)
        if not versions:
            continue
        found_any = True
        click.echo(click.style(f"\n▸ {m}", fg="green", bold=True))
        for v in versions:
            click.echo(f"  版本: {v['version_id']}  |  "
                       f"提交时间: {v['submitted_at'] or '未知'}  |  "
                       f"条目数: {v['item_count']}")

    if not found_any:
        click.echo("  暂无历史版本（覆盖导入时会自动保存旧版本）")


@cli.command("rollback", short_help="回滚周报到指定历史版本")
@click.option("-w", "--week", default=None,
              help="周起始日期 (YYYY-MM-DD)，默认本周一")
@click.option("-m", "--member", required=True,
              help="要回滚的成员名称")
@click.option("-v", "--version", "version_id", required=True,
              help="要回滚到的版本ID（通过 history 命令查看）")
def rollback_cmd(week: Optional[str], member: str, version_id: str):
    """
    回滚指定成员的周报到历史版本。

    覆盖导入前的旧版本会被自动保存，回滚后 summary 和 export 会使用旧内容。

    \b
    用法：
      python main.py history -w 2026-06-08 -m 张三    # 先查看版本列表
      python main.py rollback -w 2026-06-08 -m 张三 -v 20260608_143022  # 回滚到指定版本
    """
    storage = StorageManager()
    config = _require_init(storage)
    if config is None:
        return

    week_start = week or _get_default_week()
    click.echo(click.style(f"\n=== 回滚周报 ({week_start}) ===", fg="cyan", bold=True))

    versions = storage.list_versions(week_start, member)
    target = None
    for v in versions:
        if v["version_id"] == version_id:
            target = v
            break

    if target is None:
        click.echo(click.style(f"错误：找不到版本 {version_id}，请通过 history 命令查看可用版本", fg="red"))
        return

    storage.save_version(week_start, member)

    if storage.rollback_report(week_start, member, version_id):
        click.echo(click.style(f"✓ {member} 的周报已回滚到版本 {version_id}", fg="green"))
        click.echo(f"  版本提交时间: {target['submitted_at'] or '未知'}，条目数: {target['item_count']}")
        click.echo(f"  回滚前的版本已自动保存，可通过 history 查看")
    else:
        click.echo(click.style(f"回滚失败", fg="red"))


def main():
    cli()


if __name__ == "__main__":
    main()
