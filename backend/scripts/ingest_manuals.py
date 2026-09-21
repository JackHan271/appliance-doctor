"""冰箱手册语料入库：raw/ 下的 PDF → 解析文本 → 切分 → embedding → Milvus。

前置：已运行 scripts/reset_rag.py 清空旧语料；data/manuals/raw/ 下已放入冰箱说明书 PDF。
用法（backend 目录、已激活 venv、Milvus 服务在线）：
    python scripts/ingest_manuals.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from app.embedding import embed_texts
from app.vectordb import init_collection, insert

RAW_DIR = settings.data_dir / "manuals" / "raw"
CHUNK_SIZE = 500      # 每个片段约 500 字符
OVERLAP = 50          # 相邻片段重叠 50 字符
MIN_CHUNK = 50        # 过短片段丢弃


def extract_text(pdf_path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(pdf_path)
    pages = [(page.extract_text() or "") for page in reader.pages]
    return "\n".join(pages)


def chunk_text(text: str) -> list[str]:
    chunks = []
    step = CHUNK_SIZE - OVERLAP
    for i in range(0, len(text), step):
        chunk = text[i : i + CHUNK_SIZE].strip()
        if len(chunk) >= MIN_CHUNK:
            chunks.append(chunk)
    return chunks


def main() -> None:
    pdfs = sorted(RAW_DIR.glob("*.pdf"))
    if not pdfs:
        print(f"{RAW_DIR} 下没有 PDF。请先运行 collect_manuals.py 或手动放入冰箱说明书。")
        return

    all_chunks: list[str] = []
    for pdf in pdfs:
        # 跳过空文件/下载失败的 PDF
        if pdf.stat().st_size < 100:
            print(f"跳过 {pdf.name}（文件过小/为空，可能下载失败）")
            continue
        try:
            text = extract_text(pdf)
        except Exception as e:  # noqa: BLE001
            print(f"跳过 {pdf.name}（解析失败：{e}）")
            continue
        chunks = chunk_text(text)
        all_chunks.extend(chunks)
        print(f"{pdf.name}: {len(chunks)} 个片段（{len(text)} 字符）")

    if not all_chunks:
        print("未提取到有效文本，请检查 PDF 是否为扫描件（扫描件需 OCR）。")
        return

    print(f"共 {len(all_chunks)} 个片段，开始 embedding（首次会加载 BGE 模型）...")
    vectors = embed_texts(all_chunks)

    # embedding 完成后再连 Milvus（避免 embed 期间空闲连接被 keepalive 断开）
    init_collection()

    # 分批 insert，避免单次连接时间过长触发 Milvus 的 keepalive 限制
    BATCH = 100
    for start in range(0, len(all_chunks), BATCH):
        end = min(start + BATCH, len(all_chunks))
        insert(list(range(start, end)), vectors[start:end], all_chunks[start:end])
        print(f"已入库 {end}/{len(all_chunks)}")
    print(f"入库完成：{len(all_chunks)} 个片段已写入 Milvus")


if __name__ == "__main__":
    main()
