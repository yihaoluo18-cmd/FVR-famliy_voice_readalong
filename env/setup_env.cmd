@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

REM 在项目根目录创建 venv 并安装依赖（与 setup_env.sh 意图一致）
REM 用法：双击 或  cmd /c setup_env.cmd
REM       强制重建：setup_env.cmd --recreate
REM GPU 预装（与 setup_env.sh 的 CUDA_PIP=1 一致）： set CUDA_PIP=1 后执行本脚本

cd /d "%~dp0.."

set "RECREATE=0"
if /i "%~1"=="--recreate" set "RECREATE=1"

where py >nul 2>&1
if errorlevel 1 (
  echo [错误] 未找到 Python 启动器 py.exe。请先安装 Python 3.10+ 并勾选 Add to PATH。
  exit /b 1
)

if "%RECREATE%"=="1" (
  if exist venv (
    echo 移除已有虚拟环境 venv ...
    rmdir /s /q venv
  )
)

if exist "venv\Scripts\python.exe" (
  echo 已存在 venv，跳过创建。若要重建请运行: setup_env.cmd --recreate
  goto :pip_upgrade
)

echo [1/4] 创建虚拟环境 venv ...
py -3.11 -m venv venv 2>nul
if not exist "venv\Scripts\python.exe" (
  echo 尝试 py -3.11 失败，改用 py -3 ...
  py -3 -m venv venv
)
if not exist "venv\Scripts\python.exe" (
  echo [错误] 无法创建 venv。请确认已安装 Python 3.10+ ^(推荐 3.11^)。
  exit /b 1
)

:pip_upgrade
echo [2/4] 升级 pip / wheel / setuptools ^(<82^) ...
"venv\Scripts\python.exe" -m pip install -U pip wheel "setuptools<82"
if errorlevel 1 exit /b 1

if "%CUDA_PIP%"=="1" (
  echo [3/4] CUDA_PIP=1：预装 PyTorch CUDA 12.4 wheel ...
  "venv\Scripts\pip.exe" install torch==2.6.0 torchaudio==2.6.0 triton==3.2.0 --index-url https://download.pytorch.org/whl/cu124 --extra-index-url https://pypi.tuna.tsinghua.edu.cn/simple
  if errorlevel 1 exit /b 1
) else (
  echo [3/4] 未设置 CUDA_PIP=1，跳过 CUDA 预装。
)

echo [4/4] 安装依赖 ...
if not exist "env\requirements.txt" (
  echo [错误] 未找到 env\requirements.txt（请在发布前用运行环境执行 pip freeze ^> env\requirements.txt）
  exit /b 1
)
"venv\Scripts\pip.exe" install -r env\requirements.txt
if errorlevel 1 exit /b 1

echo.
echo 完成。Python:
"venv\Scripts\python.exe" -c "import sys; print(sys.executable)"
echo.
echo 下一步：在 Git Bash 中执行 ./start_wx_api.sh
exit /b 0
