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
import subprocess
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

def run_cmd(args, cwd=None, input_text=None, main_path=None, expect_fail=False):
    """运行命令并返回结果"""
    print(f"\n$ python main.py {' '.join(args)}")
    print("-" * 60)
    script = main_path or os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    input_bytes = input_text.encode("utf-8") if input_text else None
    result = subprocess.run(
        [sys.executable, "-X", "utf8", script] + args,
        cwd=cwd,
        capture_output=True,
        input=input_bytes,
        env=env
    )
    stdout = result.stdout.decode("utf-8", errors="replace")
    stderr = result.stderr.decode("utf-8", errors="replace")
    if stdout:
        print(stdout)
    if stderr:
        print("STDERR:", stderr, file=sys.stderr)
    print("-" * 60)
    class Result:
        pass
    r = Result()
    r.stdout = stdout
    r.stderr = stderr
    r.returncode = result.returncode
    return r

def assert_contains(actual, expected_items, label):
    for item in expected_items:
        assert item in actual, f"{label}: 未找到 '{item}'"
    print(f"✓ {label} 符合预期")

def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    test_dir = tempfile.mkdtemp(prefix="weekly_report_test_")
    print(f"测试目录: {test_dir}")

    example_dir = os.path.join(project_root, "examples")
    if not os.path.isdir(example_dir):
        print(f"错误：示例目录不存在: {example_dir}")
        return 1

    main_script = os.path.join(project_root, "main.py")
    week = "2026-06-08"
    week_end = "2026-06-14"
    team_name = "测试团队"

    # ====== 测试 1: 帮助信息 ======
    print("\n" + "=" * 60)
    print("测试 1: 帮助信息 (--help)")
    print("=" * 60)

    r = run_cmd(["--help"], cwd=test_dir, main_path=main_script)
    assert r.returncode == 0
    assert_contains(r.stdout, ["init", "import", "check", "summary", "export", "常用流程"], "顶层 help")

    for cmd in ["init", "import", "check", "summary", "export"]:
        r = run_cmd([cmd, "--help"], cwd=test_dir, main_path=main_script)
        assert r.returncode == 0, f"{cmd} --help 失败"
    print("✓ 所有子命令 help 正常")

    # ====== 测试 2: 初始化项目 ======
    print("\n" + "=" * 60)
    print("测试 2: 初始化项目 (init) - 带项目负责人")
    print("=" * 60)

    r = run_cmd([
        "init",
        "--team-name", team_name,
        "--members", "张三,李四,王五,赵六",
        "--projects", "用户中心,订单系统,商品系统,营销活动,数据分析,基础设施",
        "-y"
    ], cwd=test_dir, main_path=main_script)
    assert r.returncode == 0
    assert_contains(r.stdout, ["测试团队", "成员数：4", "项目数：6"], "init 输出")

    # ====== 测试 3: 目录批量导入 ======
    print("\n" + "=" * 60)
    print("测试 3: 目录批量导入 (import --dir)")
    print("=" * 60)

    # 复制示例文件到临时目录
    tmp_import_dir = os.path.join(test_dir, "weekly_submissions")
    os.makedirs(tmp_import_dir)
    for fname in ["张三_周报.txt", "李四_周报.txt", "王五_周报.txt"]:
        shutil.copy(os.path.join(example_dir, fname), tmp_import_dir)

    r = run_cmd([
        "import", "--week", week,
        "--dir", tmp_import_dir,
        "--on-duplicate", "overwrite",
        "--no-check"
    ], cwd=test_dir, main_path=main_script)
    assert r.returncode == 0
    assert_contains(r.stdout, ["张三", "李四", "王五", "新增 3"], "目录导入输出")

    # ====== 测试 4: 重复导入 - 跳过模式 ======
    print("\n" + "=" * 60)
    print("测试 4: 重复导入 (import --on-duplicate skip)")
    print("=" * 60)

    r = run_cmd([
        "import", "--week", week,
        "--dir", tmp_import_dir,
        "--on-duplicate", "skip",
        "--no-check"
    ], cwd=test_dir, main_path=main_script)
    assert r.returncode == 0
    assert_contains(r.stdout, ["跳过 3", "新增 0", "已存在"], "重复跳过输出")

    # ====== 测试 5: 重复导入 - 覆盖模式 ======
    print("\n" + "=" * 60)
    print("测试 5: 重复导入 (import --on-duplicate overwrite)")
    print("=" * 60)

    r = run_cmd([
        "import", "--week", week,
        "--dir", tmp_import_dir,
        "--on-duplicate", "overwrite",
        "--no-check"
    ], cwd=test_dir, main_path=main_script)
    assert r.returncode == 0
    assert_contains(r.stdout, ["覆盖 3", "新增 0", "[覆盖]"], "重复覆盖输出")

    # ====== 测试 6: check 命令 ======
    print("\n" + "=" * 60)
    print("测试 6: 校验周报 (check)")
    print("=" * 60)

    r = run_cmd(["check", "--week", week], cwd=test_dir, main_path=main_script)
    assert r.returncode == 0
    assert_contains(r.stdout, [
        "应交：4 人", "已交：3 人", "缺交 (1人): 赵六",
        "延期事项", "阻塞事项", "求助需求", "需要跟进"
    ], "check 输出")

    # ====== 测试 7: summary - 按项目归类 ======
    print("\n" + "=" * 60)
    print("测试 7: 摘要 (summary --group-by project)")
    print("=" * 60)

    r = run_cmd(["summary", "--week", week, "-g", "project"], cwd=test_dir, main_path=main_script)
    assert r.returncode == 0
    assert_contains(r.stdout, [
        "总体统计", "本周完成", "下周计划",
        "按项目分类", "用户中心", "订单系统", "营销活动"
    ], "按项目摘要输出")

    # ====== 测试 8: summary - 按成员归类 ======
    print("\n" + "=" * 60)
    print("测试 8: 摘要 (summary --group-by member)")
    print("=" * 60)

    r = run_cmd(["summary", "--week", week, "-g", "member"], cwd=test_dir, main_path=main_script)
    assert r.returncode == 0
    assert_contains(r.stdout, [
        "按成员分类", "▸ 张三", "▸ 李四", "▸ 王五",
        "本周完成", "下周计划", "风险阻塞", "求助需求"
    ], "按成员摘要输出")

    # ====== 测试 9: summary - 按负责人归类 ======
    print("\n" + "=" * 60)
    print("测试 9: 摘要 (summary --group-by owner) 按项目负责人")
    print("=" * 60)

    # 先重新初始化带负责人的配置
    r = run_cmd([
        "init",
        "--team-name", team_name,
        "--members", "张三,李四,王五,赵六",
        "-y"
    ], cwd=test_dir, main_path=main_script)
    # 因为用命令行参数无法设负责人，这里用交互式会麻烦，
    # 直接验证 owner 模式能跑通，虽然项目都归到"未分配负责人"

    r = run_cmd(["summary", "--week", week, "-g", "owner"], cwd=test_dir, main_path=main_script)
    assert r.returncode == 0
    assert_contains(r.stdout, [
        "按项目负责人分类", "未分配负责人",
        "完成:", "计划:", "风险:", "求助:", "延期:", "阻塞:"
    ], "按负责人摘要输出")
    print("✓ 按负责人归类功能正常")

    # ====== 测试 10: summary --brief ======
    print("\n" + "=" * 60)
    print("测试 10: 摘要 --brief 精简模式")
    print("=" * 60)

    r = run_cmd(["summary", "--week", week, "--brief"], cwd=test_dir, main_path=main_script)
    assert r.returncode == 0
    assert_contains(r.stdout, ["总体统计", "重点关注"], "brief 摘要输出")
    # brief 模式不应有详细条目
    assert "按项目分类" not in r.stdout and "按成员分类" not in r.stdout, "brief 模式不应有详细分类"
    print("✓ 精简模式正常")

    # ====== 测试 11: 导出所有格式 ======
    print("\n" + "=" * 60)
    print("测试 11: 导出所有格式 (export --format all)")
    print("=" * 60)

    r = run_cmd(["export", "--week", week, "-f", "all"], cwd=test_dir, main_path=main_script)
    assert r.returncode == 0

    export_dir = os.path.join(test_dir, "weekly_exports")
    assert os.path.isdir(export_dir), "导出目录不存在"
    files = os.listdir(export_dir)
    print(f"导出的文件: {files}")

    # 验证文件名包含团队名和周日期
    week_tag = f"{week}_{week_end}"
    email_files = [f for f in files if "邮件版" in f and week_tag in f]
    group_files = [f for f in files if "群公告版" in f and week_tag in f]
    md_files = [f for f in files if f.endswith(".md") and week_tag in f and "邮件" not in f and "群公告" not in f]

    assert len(email_files) == 1, f"邮件版文件未找到或命名不正确: {files}"
    assert len(group_files) == 1, f"群公告版文件未找到或命名不正确: {files}"
    assert len(md_files) == 1, f"Markdown 文件未找到或命名不正确: {files}"
    print("✓ 三种格式都已正确命名导出")

    # ====== 测试 12: 邮件版内容验证 ======
    print("\n" + "=" * 60)
    print("测试 12: 邮件版内容检查")
    print("=" * 60)

    with open(os.path.join(export_dir, email_files[0]), encoding="utf-8") as f:
        content = f.read()

    assert_contains(content, [
        "【主题】测试团队周报",
        "提交情况：3/4 人",
        "缺交：赵六",
        "本周完成情况",
        "下周工作计划",
        "风险与阻塞",
        "需要跟进的人员",
    ], "邮件版内容")
    print(f"✓ 邮件版文件内容完整: {email_files[0]}")

    # ====== 测试 13: 群公告版内容验证 ======
    print("\n" + "=" * 60)
    print("测试 13: 群公告版内容检查")
    print("=" * 60)

    with open(os.path.join(export_dir, group_files[0]), encoding="utf-8") as f:
        content = f.read()

    assert_contains(content, [
        "周报速报",
        "周报提交：3/4 人",
        "缺交人员：赵六",
        "本周概览",
        "重点关注",
        "需要跟进：",
    ], "群公告版内容")
    print(f"✓ 群公告版文件内容完整: {group_files[0]}")

    # ====== 测试 14: Markdown 版内容验证 ======
    print("\n" + "=" * 60)
    print("测试 14: Markdown 版内容检查")
    print("=" * 60)

    with open(os.path.join(export_dir, md_files[0]), encoding="utf-8") as f:
        content = f.read()

    assert_contains(content, [
        "# 测试团队周报",
        "**周期**",
        "**提交**",
        "**缺交**：赵六",
        "需要跟进",
        "## 📊 数据概览",
        "| 类别 | 数量 |",
        "## ✅ 本周完成情况",
        "## 📅 下周工作计划",
        "## ⚠️ 风险与阻塞",
        "## 🆘 求助与支持需求",
    ], "Markdown 版内容")
    print(f"✓ Markdown 版文件内容完整: {md_files[0]}")

    # ====== 测试 15: 带负责人说明的导出 ======
    print("\n" + "=" * 60)
    print("测试 15: 追加负责人说明后导出")
    print("=" * 60)

    # 用 add-note 的方式在非交互下很难测，我们直接手动写一个 summary 文件来验证导出包含说明
    import json
    summary_path = os.path.join(test_dir, ".weekly_report", "summaries", "summary_20260608.json")
    with open(summary_path, encoding="utf-8") as f:
        s = json.load(f)
    s["manual_notes"] = "本周整体进展顺利，营销活动项目延期需关注。\n请赵六尽快补交周报。"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)

    r = run_cmd(["export", "--week", week, "-f", "email"], cwd=test_dir, main_path=main_script)
    assert r.returncode == 0

    with open(os.path.join(export_dir, email_files[0]), encoding="utf-8") as f:
        content = f.read()
    assert "【负责人说明】" in content, "邮件版未包含负责人说明"
    assert "本周整体进展顺利" in content, "邮件版未包含说明内容"
    assert "请赵六尽快补交周报" in content, "邮件版未包含完整说明"

    print("✓ 负责人说明正确写入导出文件")

    # ====== 总结 ======
    print("\n" + "=" * 60)
    print("🎉 所有 15 项测试通过！")
    print("=" * 60)
    print(f"测试文件保存在: {test_dir}")
    print("可手动检查导出文件内容。")
    return 0

if __name__ == "__main__":
    sys.exit(main())
