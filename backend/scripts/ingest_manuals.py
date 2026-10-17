# -*- coding: utf-8 -*-
"""【已废弃】本脚本已被 backend/ingest.py 取代。

原因：单独的"只灌手册"脚本有两个问题
  1. 它用 init_collection()（只建不删），反复运行会让语料**重复累积**
     （实测跑 4 次后同一片段在库里存了 4 份，严重拖累检索质量）；
  2. 它不做任何语料过滤，把德语手册（海外型号）也一起灌了进去，
     中文 query 检索德语文本 = 纯噪声。

现在请用统一入口：

    python ingest.py                # 故障码 + 中文手册，分两个知识库写入
    python ingest.py --no-manuals   # 只入故障码
"""
import sys

print(__doc__)
print("请改用：python ingest.py")
sys.exit(1)
