@echo off
title Milvus - DO NOT CLOSE
cd /d "%~dp0"
call .venv\Scripts\activate.bat

echo ============================================================
echo   Milvus 向量库服务
echo.
echo   启动后请保持此窗口开着，不要关闭、也不要拿它跑别的命令。
echo   关掉它，RAG 检索就会失效（连接被拒绝或返回空）。
echo.
echo   [正常状态] 一直停在监听 19530 的日志上不动。
echo ============================================================
echo.

milvus-lite server --data-dir ./milvus_data --port 19530

echo.
echo ------------------------------------------------------------
echo   Milvus 已退出，按任意键关闭窗口。
echo ------------------------------------------------------------
pause >nul
