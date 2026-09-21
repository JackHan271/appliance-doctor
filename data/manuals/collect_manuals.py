"""
手册语料采集脚本（用户在本机运行）

用途：从公开来源下载冰箱/洗衣机说明书 PDF，作为 RAG 语料。
合规：仅用于个人本地 demo，不公开分发、不商用（见 docs/05-数据策略.md）。

用法：
1. 在 SOURCES 列表填入说明书 PDF 直链（优先厂商官网）。
2. 运行：python collect_manuals.py
3. 下载文件保存到 manuals/raw/ 目录。
"""
import os
import time
import urllib.request

RAW_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "raw")

SOURCES = [
    # 西门子冰箱说明书（中文 PDF，官网直链）
    "https://media3.bsh-group.com/Documents/8001225533_E.pdf",
    "https://media3.bsh-group.com/Documents/8001108606_B.pdf",
    "https://media3.bsh-group.com/Documents/8001108154_A.pdf",
    # 美的冰箱维修手册（海外型号，官方 content/dam 直链，法语 service manual）
    "https://www.midea.com/content/dam/midea-aem/fr/service-manual/ref/Service-manual-REF-MDRB600MME46.pdf",
    # 海尔：中国官网说明书为 H5 格式，无稳定 PDF 直链，请手动下载放到 raw/
]

HEADERS = {"User-Agent": "Mozilla/5.0 (personal-archival)"}


def main() -> None:
    os.makedirs(RAW_DIR, exist_ok=True)
    if not SOURCES:
        print("请先在 SOURCES 列表填入说明书 PDF 直链。")
        return
    for i, url in enumerate(SOURCES, 1):
        name = url.rstrip("/").split("/")[-1] or f"doc_{i}.pdf"
        dest = os.path.join(RAW_DIR, name)
        print(f"[{i}/{len(SOURCES)}] 下载 {url}")
        req = urllib.request.Request(url, headers=HEADERS)
        try:
            with urllib.request.urlopen(req, timeout=60) as r, open(dest, "wb") as f:
                f.write(r.read())
            print(f"  已保存 {dest}")
        except Exception as e:  # noqa: BLE001
            print(f"  失败：{e}")
        time.sleep(1.5)  # 礼貌限速


if __name__ == "__main__":
    main()
