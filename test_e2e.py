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

def run_cmd(args, cwd=None, input_text=None, main_path=None):
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

def main():
    project_root = os.path.dirname(os.path.abspath(__file__))
    test_dir = tempfile.mkdtemp(prefix="weekly_report_test_")
    print(f"测试目录: {test_dir}")

    example_dir = os.path.join(project_root, "examples")
    if not os.path.isdir(example_dir):
        print(f"错误：示例目录不存在: {example_dir}")
        return 1

    os.chdir(test_dir)

    print("\n" + "=" * 60)
    print("测试 1: 初始化项目 (init)")
    print("=" * 60)

    main_script = os.path.join(project_root, "main.py")

    r = run_cmd([
        "init",
        "--team-name", "测试团队",
        "--members", "张三,李四,王五,赵六",
        "--projects", "用户中心,订单系统,商品系统,营销活动,数据分析,基础设施"
    ], cwd=test_dir, main_path=main_script)
    if r.returncode != 0:
        print("初始化失败")
        return 1

    print("\n" + "=" * 60)
    print("测试 2: 导入周报 (import) - 导入3份，赵六缺交")
    print("=" * 60)

    example_files = [
        os.path.join(example_dir, "张三_周报.txt"),
        os.path.join(example_dir, "李四_周报.txt"),
        os.path.join(example_dir, "王五_周报.txt"),
    ]
    r = run_cmd(["import", "--week", "2026-06-08"] + example_files, cwd=test_dir, main_path=main_script)
    if r.returncode != 0:
        print("导入失败")
        return 1

    print("\n" + "=" * 60)
    print("测试 3: 校验周报 (check) - 检测缺交、延期、阻塞")
    print("=" * 60)

    r = run_cmd(["check", "--week", "2026-06-08"], cwd=test_dir, main_path=main_script)
    if r.returncode != 0:
        print("校验失败")
        return 1

    output = r.stdout
    assert "缺交" in output and "赵六" in output, "未检测到缺交人员赵六"
    assert "延期事项" in output, "未识别延期事项"
    assert "阻塞事项" in output, "未识别阻塞事项"
    assert "求助需求" in output, "未识别求助需求"
    assert "需要跟进" in output, "未列出需要跟进人员"
    print("✓ check 检测结果符合预期")

    print("\n" + "=" * 60)
    print("测试 4: 生成摘要 (summary) - 按项目归类")
    print("=" * 60)

    r = run_cmd(["summary", "--week", "2026-06-08", "--group-by", "project"], cwd=test_dir, main_path=main_script)
    if r.returncode != 0:
        print("摘要生成失败")
        return 1
    print("✓ 按项目摘要生成成功")

    print("\n" + "=" * 60)
    print("测试 5: 生成摘要 (summary) - 按成员归类")
    print("=" * 60)

    r = run_cmd(["summary", "--week", "2026-06-08", "--group-by", "member"], cwd=test_dir, main_path=main_script)
    if r.returncode != 0:
        print("成员摘要生成失败")
        return 1
    print("✓ 按成员摘要生成成功")

    print("\n" + "=" * 60)
    print("测试 6: 导出周报 (export) - 同时导出两种格式")
    print("=" * 60)

    r = run_cmd(["export", "--week", "2026-06-08", "--format", "both"], cwd=test_dir, main_path=main_script)
    if r.returncode != 0:
        print("导出失败")
        return 1

    export_dir = os.path.join(test_dir, "weekly_exports")
    files = os.listdir(export_dir)
    email_file = [f for f in files if "邮件" in f]
    group_file = [f for f in files if "群公告" in f]
    assert len(email_file) == 1, "邮件格式未生成"
    assert len(group_file) == 1, "群公告格式未生成"

    with open(os.path.join(export_dir, email_file[0]), encoding="utf-8") as f:
        content = f.read()
        assert "本周完成情况" in content
        assert "下周工作计划" in content
    print(f"✓ 邮件格式导出成功: {email_file[0]}")

    with open(os.path.join(export_dir, group_file[0]), encoding="utf-8") as f:
        content = f.read()
        assert "周报速报" in content
        assert "本周概览" in content
    print(f"✓ 群公告格式导出成功: {group_file[0]}")

    print("\n" + "=" * 60)
    print("🎉 所有测试通过！")
    print("=" * 60)
    print(f"测试文件保存在: {test_dir}")
    print("可手动检查导出文件内容。")
    return 0

if __name__ == "__main__":
    sys.exit(main())
