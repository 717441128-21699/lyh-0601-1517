from setuptools import setup, find_packages

setup(
    name="weekly-report-tool",
    version="1.0.0",
    description="团队周报汇总命令行工具",
    packages=find_packages(),
    install_requires=[
        "click>=8.1.0",
        "openpyxl>=3.1.0",
        "PyYAML>=6.0",
        "tabulate>=0.9.0",
    ],
    entry_points={
        "console_scripts": [
            "weekly-report=weekly_report_tool.cli:main",
            "wrt=weekly_report_tool.cli:main",
        ],
    },
    python_requires=">=3.8",
)
