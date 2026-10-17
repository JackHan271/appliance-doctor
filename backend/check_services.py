# -*- coding: utf-8 -*-
"""一键服务体检：检查 Milvus 与后端是否在监听。

零依赖（只用标准库），**不需要激活虚拟环境**，任何目录都能跑。

用法：
    python check_services.py
"""
import socket
import sys

sys.stdout.reconfigure(encoding="utf-8")

SERVICES = [
    ("Milvus 向量库", "127.0.0.1", 19530),
    ("后端服务", "127.0.0.1", 8000),
]


def port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def main() -> int:
    print("=" * 58)
    print("服务体检")
    print("=" * 58)

    all_up = True
    for name, host, port in SERVICES:
        up = port_open(host, port)
        all_up = all_up and up
        mark = "✓" if up else "✗"
        state = "监听中" if up else "未启动"
        print(f"  [{mark}] {name:<14} {host}:{port:<6} {state}")

    print()
    if all_up:
        print("✅ 两个服务都在跑，可以执行诊断 / 评估脚本了。")
        return 0

    print("⚠ 有服务没启动。启动方式（在 backend 目录下）：")
    print()
    print("   方式一：双击")
    print("     启动Milvus.bat     （窗口标题会写「请勿关闭」）")
    print("     启动后端.bat")
    print()
    print("   方式二：命令行（两个窗口各跑一条，都保持开着）")
    print("     cd C:\\Users\\ASUS\\Desktop\\appliance-doctor\\backend; .venv\\Scripts\\activate; milvus-lite server --data-dir ./milvus_data --port 19530")
    print("     cd C:\\Users\\ASUS\\Desktop\\appliance-doctor\\backend; .venv\\Scripts\\activate; uvicorn app.main:app --reload")
    print()
    print("   注：Milvus 是前台进程，窗口关掉它就停了。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
