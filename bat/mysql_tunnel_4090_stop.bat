@echo off
setlocal

set "LOCAL_PORT=3308"
if not "%~1"=="" set "LOCAL_PORT=%~1"

echo [INFO] 查找监听本地端口 %LOCAL_PORT% 的进程...
set "FOUND="
for /f "tokens=5" %%p in ('netstat -aon ^| findstr /r /c:":%LOCAL_PORT% .*LISTENING"') do (
  set "FOUND=1"
  echo [INFO] 结束隧道进程 PID=%%p
  taskkill /PID %%p /F >nul 2>&1
)

if not defined FOUND (
  echo [WARN] 未发现监听 %LOCAL_PORT% 的进程，可能已关闭。
) else (
  echo [OK] 已尝试关闭本地端口 %LOCAL_PORT% 的隧道。
)
pause