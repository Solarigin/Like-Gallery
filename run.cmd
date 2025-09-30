@echo off
setlocal EnableExtensions EnableDelayedExpansion

set "ROOT_DIR=%~dp0"
if "%ROOT_DIR:~-1%"=="\" set "ROOT_DIR=%ROOT_DIR:~0,-1%"
set "APP_DIR=%ROOT_DIR%\sia-desktop"
set "VENV_DIR=%ROOT_DIR%\.venv"
set "EXIT_CODE=0"
set "PUSHED="

pushd "%ROOT_DIR%" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] 无法进入项目目录 %ROOT_DIR%。
  set "EXIT_CODE=1"
  goto :exit
)
set "PUSHED=1"

set "PYTHON_EXE="
set "PYTHON_ARGS="

if defined PYTHON (
  call :parse_python "%PYTHON%"
) else (
  for %%C in ("py|-3.12" "py|-3.11" "py|-3.10" "py|-3" "python3" "python") do (
    if not defined PYTHON_EXE (
      for /f "tokens=1,2 delims=|" %%I in ("%%~C") do (
        call :test_python "%%~I" "%%~J"
      )
    )
  )
)

if not defined PYTHON_EXE (
  echo [ERROR] 未找到可用的 Python 3.10+ 解释器。请安装 Python 3.10 及以上版本，或设置 PYTHON 环境变量后重试。
  set "EXIT_CODE=1"
  goto :exit
)

echo [INFO] 使用 Python 解释器: %PYTHON_EXE% %PYTHON_ARGS%

if not exist "%VENV_DIR%\Scripts\python.exe" (
  echo [INFO] 创建虚拟环境 "%VENV_DIR%"
  call :run_python -m venv "%VENV_DIR%"
  if errorlevel 1 (
    echo [ERROR] 创建虚拟环境失败。
    set "EXIT_CODE=1"
    goto :exit
  )
)

call "%VENV_DIR%\Scripts\activate.bat"
if errorlevel 1 (
  echo [ERROR] 激活虚拟环境失败。
  set "EXIT_CODE=1"
  goto :exit
)

if exist "%VENV_DIR%\Scripts\python.exe" (
  set "PYTHON_EXE=%VENV_DIR%\Scripts\python.exe"
  set "PYTHON_ARGS="
  echo [INFO] 切换到虚拟环境解释器: %PYTHON_EXE%
) else (
  echo [ERROR] 未找到虚拟环境解释器: %VENV_DIR%\Scripts\python.exe
  set "EXIT_CODE=1"
  goto :exit
)

call :run_python -m pip install --upgrade pip wheel
if errorlevel 1 goto :pip_error
call :run_python -m pip install -e "%APP_DIR%"
if errorlevel 1 goto :pip_error

set "_TMP_PORT=%TEMP%\sia_port_%RANDOM%.txt"
call :run_python -c "from sia.core.config import CONFIG; print(CONFIG.get().port)" >"%_TMP_PORT%"
if errorlevel 1 goto :python_error
set /p PORT=<"%_TMP_PORT%"
del "%_TMP_PORT%" >nul 2>&1

call :run_python -c ^
"from sia.core.config import CONFIG; ^
cfg = CONFIG.get(); ^
cfg.base_dir.mkdir(parents=True, exist_ok=True); ^
images = cfg.base_dir / 'images.json'; ^
import json; ^
if not images.exists(): ^
    images.write_text('[]', encoding='utf-8'); ^
print('图库目录:', cfg.base_dir); ^
print('索引文件:', images)"
if errorlevel 1 goto :python_error

echo [INFO] 启动服务: http://127.0.0.1:%PORT%
call :run_python -m uvicorn sia.server.api:app --host 0.0.0.0 --port %PORT%
set "EXIT_CODE=%errorlevel%"
goto :exit

:pip_error
echo [ERROR] 依赖安装失败。
set "EXIT_CODE=1"
goto :exit

:python_error
echo [ERROR] 初始化图库目录失败。
if defined _TMP_PORT if exist "%_TMP_PORT%" del "%_TMP_PORT%" >nul 2>&1
set "EXIT_CODE=1"
goto :exit

:parse_python
set "PYTHON_CMD=%~1"
for /f "tokens=1*" %%I in ("%PYTHON_CMD%") do (
  set "PYTHON_EXE=%%~I"
  set "PYTHON_ARGS=%%~J"
)
exit /b

:test_python
set "_EXE=%~1"
set "_ARGS=%~2"
call :run_command "%_EXE%" %_ARGS% -c "import sys; assert sys.version_info >= (3, 10)" >nul 2>&1
if not errorlevel 1 (
  set "PYTHON_EXE=%_EXE%"
  set "PYTHON_ARGS=%_ARGS%"
)
exit /b

:run_python
call :run_command "%PYTHON_EXE%" %PYTHON_ARGS% %*
exit /b %errorlevel%

:run_command
set "_EXE=%~1"
shift
"%_EXE%" %*
exit /b %errorlevel%

:exit
if defined PUSHED popd >nul 2>&1
set "_EXIT=%EXIT_CODE%"
endlocal & exit /b %_EXIT%
