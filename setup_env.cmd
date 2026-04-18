@echo off
chcp 65001 >nul
setlocal

REM 根目录一键环境初始化入口（实际逻辑在 env\setup_env.cmd）
cd /d "%~dp0"
call "%~dp0env\setup_env.cmd" %*
exit /b %errorlevel%
