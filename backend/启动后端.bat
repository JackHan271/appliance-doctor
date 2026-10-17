@echo off
title Backend - DO NOT CLOSE
cd /d "%~dp0"
call .venv\Scripts\activate.bat

echo ============================================================
echo   后端服务 FastAPI + LangGraph
echo.
echo   前置 Milvus 已经在跑，先双击 启动Milvus.bat
echo   启动成功后访问 http://127.0.0.1:8000/health 应返回 ok
echo   请保持此窗口开着。
echo ============================================================
echo.

uvicorn app.main:app --reload

echo.
echo ------------------------------------------------------------
echo   后端已退出，按任意键关闭窗口。
echo ------------------------------------------------------------
pause >nul
