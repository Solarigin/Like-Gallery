@echo off
setlocal EnableExtensions EnableDelayedExpansion

if /i "%~1"=="--no-pause" (
  set "SIA_NO_PAUSE=1"
  shift
)

rem ---------------------------------------------------------------------------
rem  Detect project directories
rem ---------------------------------------------------------------------------
set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
set "EXIT_CODE=0"
set "PUSHED="

pushd "%ROOT_DIR%" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] 无法进入项目根目录 "%ROOT_DIR%"。
  set "EXIT_CODE=1"
  goto :cleanup
)
set "PUSHED=1"

set "APP_DIR=%ROOT_DIR%\sia-desktop"
set "VENV_DIR=%ROOT_DIR%\.venv"
set "PYTHON_EXE="
set "PYTHON_ARGS="

if not exist "%APP_DIR%" (
  echo [ERROR] 未找到应用程序目录: %APP_DIR%
  set "EXIT_CODE=1"
  goto :cleanup
)

rem ---------------------------------------------------------------------------
rem  Locate a Python 3.10+ interpreter
rem ---------------------------------------------------------------------------
call :find_python
if not defined PYTHON_EXE (
  echo [ERROR] 未找到可用的 Python 3.10 及以上版本。请安装或在 PYTHON 环境变量中指定解释器路径。
  set "EXIT_CODE=1"
  goto :cleanup
)

if defined PYTHON_ARGS (
  echo [INFO] 使用 Python 解释器: %PYTHON_EXE% %PYTHON_ARGS%
) else (
  echo [INFO] 使用 Python 解释器: %PYTHON_EXE%
)

rem ---------------------------------------------------------------------------
rem  Prepare virtual environment
rem ---------------------------------------------------------------------------
if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo [INFO] 创建虚拟环境 "%VENV_DIR%"
  call :run_python -m venv "%VENV_DIR%"
  if errorlevel 1 (
    echo [ERROR] 创建虚拟环境失败。
    set "EXIT_CODE=1"
    goto :cleanup
  )
)

set "VENV_PY=%VENV_DIR%\Scripts\python.exe"
if not exist "%VENV_PY%" (
  echo [ERROR] 未找到虚拟环境解释器: %VENV_PY%
  set "EXIT_CODE=1"
  goto :cleanup
)

rem ---------------------------------------------------------------------------
rem  Install/update dependencies inside the virtual environment
rem ---------------------------------------------------------------------------
echo [INFO] 更新 pip 并安装必要依赖...
"%VENV_PY%" -m pip install --upgrade pip
if errorlevel 1 goto :pip_error
"%VENV_PY%" -m pip install -e "%APP_DIR%"
if errorlevel 1 goto :pip_error

rem ---------------------------------------------------------------------------
rem  Ensure gallery data directory is ready
rem ---------------------------------------------------------------------------
echo [INFO] 检查图库配置...
"%VENV_PY%" -c "from sia.core.config import CONFIG; cfg = CONFIG.get(); cfg.base_dir.mkdir(parents=True, exist_ok=True); images = cfg.base_dir / 'images.json'; _ = images.exists() or images.write_text('[]', encoding='utf-8'); print('图库目录:', cfg.base_dir); print('索引文件:', images)"
if errorlevel 1 goto :python_error

rem ---------------------------------------------------------------------------
rem  Launch the desktop application
rem ---------------------------------------------------------------------------
echo [INFO] 启动 Like-Gallery 桌面应用...
"%VENV_PY%" -m sia.app
set "EXIT_CODE=%errorlevel%"
goto :cleanup

:pip_error
echo [ERROR] 依赖安装失败。
set "EXIT_CODE=1"
goto :cleanup

:python_error
echo [ERROR] 初始化图库目录失败。
set "EXIT_CODE=1"
goto :cleanup

:find_python
if defined PYTHON (
  call :parse_custom_python "%PYTHON%"
  if defined PYTHON_EXE exit /b
)
for %%C in ("py|-3.12" "py|-3.11" "py|-3.10" "py|-3" "python3" "python") do (
  if not defined PYTHON_EXE (
    for /f "tokens=1,2 delims=|" %%I in ("%%~C") do (
      call :test_python "%%~I" "%%~J"
    )
  )
)
exit /b

:parse_custom_python
set "PYTHON_CMD=%~1"
for /f "tokens=1*" %%I in ("%PYTHON_CMD%") do (
  set "PYTHON_EXE=%%~I"
  set "PYTHON_ARGS=%%~J"
)
call :test_python "%PYTHON_EXE%" "%PYTHON_ARGS%"
if errorlevel 1 (
  set "PYTHON_EXE="
  set "PYTHON_ARGS="
)
exit /b

:test_python
set "_EXE=%~1"
set "_ARGS=%~2"
if defined _ARGS (
  "%_EXE%" %_ARGS% -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
) else (
  "%_EXE%" -c "import sys; exit(0 if sys.version_info >= (3, 10) else 1)" >nul 2>&1
)
if not errorlevel 1 (
  set "PYTHON_EXE=%_EXE%"
  set "PYTHON_ARGS=%_ARGS%"
  exit /b 0
)
exit /b 1

:run_python
set "_RC=0"
if defined PYTHON_ARGS (
  "%PYTHON_EXE%" %PYTHON_ARGS% %*
) else (
  "%PYTHON_EXE%" %*
)
set "_RC=%errorlevel%"
exit /b %_RC%

:cleanup
if defined PUSHED popd >nul 2>&1
set "_RC=%EXIT_CODE%"
if not defined SIA_NO_PAUSE pause
endlocal & exit /b %_RC%
