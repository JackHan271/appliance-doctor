FROM python:3.12-slim

# Milvus 向量库（milvus-lite server 模式）
# 注意：milvus-lite 的 server 模式依赖 pymilvus 的 grpc_gen 模块，
# 所以用官方推荐的 pymilvus[milvus-lite] 一次装齐（漏装 pymilvus 会报
# "No module named 'pymilvus'"）。
# 生产环境可替换为 milvusdb/milvus standalone 或 Zilliz Cloud。

RUN pip install --no-cache-dir "pymilvus[milvus-lite]" -i https://pypi.tuna.tsinghua.edu.cn/simple

VOLUME /milvus_data
EXPOSE 19530

CMD ["milvus-lite", "server", "--data-dir", "/milvus_data", "--port", "19530"]
