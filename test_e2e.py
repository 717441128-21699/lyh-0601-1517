#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
端到端测试脚本：验证团队周报汇总工具的完整功能
使用方法：python test_e2e.py
"""
import os
import sys
import shutil
import tempfile
import json
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from click.testing import CliRunner
from weekly_report_tool.cli import cli
from weekly_report_tool.models import TeamSummary, ItemType
from weekly_report_tool.storage import StorageManager


def assert_contains(actual, expected_items, label):
    for item in expected_items:
        assert item in actual, f"{label}: 未找到 '{item}'"
    print(f"✓ {label} 符合预期")


def main():
    runner = CliRunner()
    test_dir = tempfile.mkdtemp(prefix="weekly_report_test_")
    os.chdir(test_dir)
    print(f"测试目录: {test_dir}")

    example_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples")
    submissions_dir = os.path.join(test_dir, "submissions")
    os.makedirs(submissions_dir)
    for f in os.listdir(example_dir):
        if f.endswith('.txt'):
            shutil.copy(os.path.join(example_dir, f), submissions_dir)

    week = "2026-06-08"
    week_end = "2026-06-14"
    team_name = "测试团队"

    # ====== 测试 1: 帮助信息 ======
    print("\n" + "=" * 60)
    print("测试 1: 帮助信息 (--help)")
    print("=" * 60)

    r = runner.invoke(cli, ['--help'])
    assert r.exit_code == 0
    assert_contains(r.output, ["init", "import", "check", "summary", "export", "常用流程"], "顶层 help")

    for cmd in ["init", "import", "check", "summary", "export"]:
        r2 = runner.invoke(cli, [cmd, '--help'])
        assert r2.exit_code == 0, f"{cmd} --help 失败"
    print("✓ 所有子命令 help 正常")

    # ====== 测试 2: 初始化项目 ======
    print("\n" + "=" * 60)
    print("测试 2: 初始化项目 (init)")
    print("=" * 60)

    r = runner.invoke(cli, ['init', '--team-name', team_name,
                            '--members', '张三,李四,王五,赵六',
                            '--projects', '用户中心,订单系统,商品系统,营销活动,数据分析,基础设施',
                            '-y'])
    assert r.exit_code == 0
    assert_contains(r.output, ["测试团队", "成员数：4", "项目数：6"], "init 输出")

    # ====== 测试 3: 目录批量导入 ======
    print("\n" + "=" * 60)
    print("测试 3: 目录批量导入 (import --dir)")
    print("=" * 60)

    r = runner.invoke(cli, ['import', '--week', week, '--dir', submissions_dir,
                            '--on-duplicate', 'overwrite', '--no-check'])
    assert r.exit_code == 0
    assert_contains(r.output, ["张三", "李四", "王五", "新增 3"], "目录导入输出")

    # ====== 测试 4: 重复导入 - 跳过 ======
    print("\n" + "=" * 60)
    print("测试 4: 重复导入 (skip)")
    print("=" * 60)

    r = runner.invoke(cli, ['import', '--week', week, '--dir', submissions_dir,
                            '--on-duplicate', 'skip', '--no-check'])
    assert r.exit_code == 0
    assert_contains(r.output, ["跳过 3", "新增 0", "已存在"], "重复跳过输出")

    # ====== 测试 5: 重复导入 - 覆盖 ======
    print("\n" + "=" * 60)
    print("测试 5: 重复导入 (overwrite)")
    print("=" * 60)

    r = runner.invoke(cli, ['import', '--week', week, '--dir', submissions_dir,
                            '--on-duplicate', 'overwrite', '--no-check'])
    assert r.exit_code == 0
    assert_contains(r.output, ["覆盖 3", "新增 0", "[覆盖]"], "重复覆盖输出")

    # ====== 测试 6: check 命令 ======
    print("\n" + "=" * 60)
    print("测试 6: 校验周报 (check)")
    print("=" * 60)

    r = runner.invoke(cli, ['check', '--week', week])
    assert r.exit_code == 0
    assert_contains(r.output, [
        "应交：4 人", "已交：3 人", "赵六",
        "延期", "阻塞", "求助", "需要跟进"
    ], "check 输出")

    # ====== 测试 7: import 自动 check ======
    print("\n" + "=" * 60)
    print("测试 7: import 自动 check")
    print("=" * 60)

    r = runner.invoke(cli, ['import', '--week', week, '--dir', submissions_dir,
                            '--on-duplicate', 'overwrite'])
    assert r.exit_code == 0
    assert "导入完成" in r.output
    assert "提交情况" in r.output
    print("✓ 导入后自动执行 check")

    # ====== 测试 8: summary 按项目 ======
    print("\n" + "=" * 60)
    print("测试 8: summary --group-by project")
    print("=" * 60)

    r = runner.invoke(cli, ['summary', '--week', week, '-g', 'project'])
    assert r.exit_code == 0
    assert_contains(r.output, [
        "总体统计", "按项目分类", "用户中心", "订单系统"
    ], "按项目摘要输出")

    # ====== 测试 9: summary 按成员 ======
    print("\n" + "=" * 60)
    print("测试 9: summary --group-by member")
    print("=" * 60)

    r = runner.invoke(cli, ['summary', '--week', week, '-g', 'member'])
    assert r.exit_code == 0
    assert_contains(r.output, [
        "按成员分类", "张三", "李四", "王五"
    ], "按成员摘要输出")

    # ====== 测试 10: summary 按负责人 (不重复) ======
    print("\n" + "=" * 60)
    print("测试 10: summary --group-by owner (不重复统计)")
    print("=" * 60)

    r = runner.invoke(cli, ['summary', '--week', week, '-g', 'owner'])
    assert r.exit_code == 0
    assert_contains(r.output, [
        "按项目负责人分类", "未分配负责人"
    ], "按负责人摘要输出")

    storage = StorageManager()
    reports = storage.load_all_reports_for_week(week)
    actual_completed = sum(len(rep.get_items_by_type(ItemType.COMPLETED)) for rep in reports.values())

    import re
    owner_completed = 0
    for line in r.output.split('\n'):
        if '完成:' in line and '计划:' in line:
            m = re.search(r'完成:(\d+)', line)
            if m:
                owner_completed += int(m.group(1))

    assert owner_completed == actual_completed, \
        f"owner 视图完成数 {owner_completed} != 实际 {actual_completed}"
    print(f"✓ owner 视图完成数 = {actual_completed}，无重复统计")

    # ====== 测试 11: summary --brief ======
    print("\n" + "=" * 60)
    print("测试 11: summary --brief")
    print("=" * 60)

    r = runner.invoke(cli, ['summary', '--week', week, '--brief'])
    assert r.exit_code == 0
    assert_contains(r.output, ["总体统计", "重点关注"], "brief 摘要输出")
    assert "按项目分类" not in r.output and "按成员分类" not in r.output, "brief 模式不应有详细分类"
    print("✓ 精简模式正常")

    # ====== 测试 12: 导出所有格式 ======
    print("\n" + "=" * 60)
    print("测试 12: export --format all")
    print("=" * 60)

    r = runner.invoke(cli, ['export', '--week', week, '-f', 'all'])
    assert r.exit_code == 0

    export_dir = os.path.join(test_dir, "weekly_exports")
    assert os.path.isdir(export_dir), "导出目录不存在"
    files = os.listdir(export_dir)
    print(f"导出的文件: {files}")

    week_tag = f"{week}_{week_end}"
    email_files = [f for f in files if "邮件版" in f and week_tag in f]
    group_files = [f for f in files if "群公告版" in f and week_tag in f]
    md_files = [f for f in files if f.endswith(".md") and week_tag in f and "邮件" not in f and "群公告" not in f]

    assert len(email_files) == 1, f"邮件版文件问题: {files}"
    assert len(group_files) == 1, f"群公告版文件问题: {files}"
    assert len(md_files) == 1, f"Markdown 文件问题: {files}"
    print("✓ 三种格式都已正确命名导出")

    # ====== 测试 13: 邮件版内容验证 ======
    print("\n" + "=" * 60)
    print("测试 13: 邮件版内容检查")
    print("=" * 60)

    with open(os.path.join(export_dir, email_files[0]), encoding="utf-8") as f:
        content = f.read()
    assert_contains(content, [
        "【主题】测试团队周报", "缺交：赵六",
        "本周完成情况", "下周工作计划", "风险与阻塞", "需要跟进的人员",
    ], "邮件版内容")
    print(f"✓ 邮件版文件内容完整: {email_files[0]}")

    # ====== 测试 14: 群公告版内容验证 ======
    print("\n" + "=" * 60)
    print("测试 14: 群公告版内容检查")
    print("=" * 60)

    with open(os.path.join(export_dir, group_files[0]), encoding="utf-8") as f:
        content = f.read()
    assert_contains(content, [
        "周报速报", "缺交人员：赵六", "需要跟进：",
    ], "群公告版内容")
    print(f"✓ 群公告版文件内容完整: {group_files[0]}")

    # ====== 测试 15: Markdown 版内容验证 ======
    print("\n" + "=" * 60)
    print("测试 15: Markdown 版内容检查")
    print("=" * 60)

    with open(os.path.join(export_dir, md_files[0]), encoding="utf-8") as f:
        content = f.read()
    assert_contains(content, [
        "# 测试团队周报", "**缺交**", "需要跟进",
        "| 类别 | 数量 |",
    ], "Markdown 版内容")
    print(f"✓ Markdown 版文件内容完整: {md_files[0]}")

    # ====== 测试 16: 负责人说明 ======
    print("\n" + "=" * 60)
    print("测试 16: 追加负责人说明后导出")
    print("=" * 60)

    summary_path = os.path.join(test_dir, ".weekly_report", "summaries", "summary_20260608.json")
    with open(summary_path, encoding="utf-8") as f:
        s = json.load(f)
    s["manual_notes"] = "本周整体进展顺利，营销活动项目延期需关注。\n请赵六尽快补交周报。"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)

    r = runner.invoke(cli, ['export', '--week', week, '-f', 'email'])
    assert r.exit_code == 0

    with open(os.path.join(export_dir, email_files[0]), encoding="utf-8") as f:
        content = f.read()
    assert "【负责人说明】" in content
    assert "本周整体进展顺利" in content
    print("✓ 负责人说明正确写入导出文件")

    # ====== 测试 17: ask 模式 - 跳过 ======
    print("\n" + "=" * 60)
    print("测试 17: ask 模式选择跳过，旧数据不变")
    print("=" * 60)

    ask_v2_path = os.path.join(submissions_dir, "ask_test_v2.txt")
    with open(ask_v2_path, "w", encoding="utf-8") as f:
        f.write("姓名：张三\n周期：2026-06-08 ~ 2026-06-14\n\n本周完成：\n- ASK_V2_测试内容\n")

    r = runner.invoke(cli, ['import', '--week', week, ask_v2_path,
                            '--on-duplicate', 'ask', '--no-check'], input="n\n")
    assert r.exit_code == 0
    assert '跳过' in r.output

    report = storage.load_report(week, '张三')
    has_v2 = any('ASK_V2_测试内容' in it.content for it in report.items)
    assert not has_v2, "跳过后不应有新内容"
    print("✓ ask 跳过后旧数据保持不变")

    # ====== 测试 18: ask 模式 - 覆盖 ======
    print("\n" + "=" * 60)
    print("测试 18: ask 模式选择覆盖，summary/export 看到新内容")
    print("=" * 60)

    r = runner.invoke(cli, ['import', '--week', week, ask_v2_path,
                            '--on-duplicate', 'ask', '--no-check'], input="y\n")
    assert r.exit_code == 0
    assert '覆盖' in r.output

    r = runner.invoke(cli, ['summary', '--week', week, '-g', 'member'])
    assert 'ASK_V2_测试内容' in r.output, "覆盖后 summary 看不到新内容"

    r = runner.invoke(cli, ['export', '--week', week, '-f', 'email'])
    with open(os.path.join(export_dir, email_files[0]), encoding="utf-8") as f:
        content = f.read()
    assert 'ASK_V2_测试内容' in content, "覆盖后 export 看不到新内容"
    print("✓ ask 覆盖后 summary/export 能看到新内容")

    # ====== 测试 19: Excel 多 sheet + 空 sheet ======
    print("\n" + "=" * 60)
    print("测试 19: Excel 多 sheet + 空 sheet 导入")
    print("=" * 60)

    from openpyxl import Workbook
    excel_test_dir = tempfile.mkdtemp(prefix="wr_excel_e2e_")
    old_cwd = os.getcwd()
    os.chdir(excel_test_dir)

    try:
        wb = Workbook()
        ws1 = wb.active
        ws1.title = "张三Excel"
        ws1.append(["姓名：张三Excel"])
        ws1.append(["周期：2026-06-08 ~ 2026-06-14"])
        ws1.append([])
        ws1.append(["本周完成："])
        ws1.append(["- 【用户中心】完成Excel导入测试"])

        wb.create_sheet("空Sheet")

        ws3 = wb.create_sheet("李四Excel")
        ws3.append(["姓名：李四Excel"])
        ws3.append(["本周完成："])
        ws3.append(["- 【订单系统】完成Excel导出功能"])

        xlsx_path = os.path.join(excel_test_dir, "excel_test.xlsx")
        wb.save(xlsx_path)

        r = runner.invoke(cli, ['init', '--team-name', 'Excel团队',
                                '--members', '张三Excel,李四Excel,王五',
                                '--projects', '用户中心,订单系统', '-y'])
        assert r.exit_code == 0

        r = runner.invoke(cli, ['import', '--week', '2026-06-08', xlsx_path,
                                '--on-duplicate', 'overwrite', '--no-check'])
        assert r.exit_code == 0, f"Excel import failed: {r.output}"
        assert '新增 2' in r.output, f"Excel import output: {r.output}"

        r = runner.invoke(cli, ['check', '--week', '2026-06-08'])
        assert '应交：3 人' in r.output, f"check output: {r.output}"
        assert '已交：2 人' in r.output, f"check output: {r.output}"
        assert '王五' in r.output, f"check output: {r.output}"
    finally:
        os.chdir(old_cwd)
    print("✓ Excel 多 sheet + 空 sheet 导入正常")

    # ====== 总结 ======
    print("\n" + "=" * 60)
    print("🎉 所有 19 项测试通过！")
    print("=" * 60)
    print(f"测试文件保存在: {test_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
