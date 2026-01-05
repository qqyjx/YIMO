@echo off
setlocal enabledelayedexpansion

REM === 配置区：如需修改端口，在这里改 LOCAL_PORT 即可 ===
set "LOCAL_PORT=3308"
set "REMOTE_HOST=192.168.1.123"
set "REMOTE_USER=xdx"
set "JUMP_ALIAS=JumpMachine"

REM 允许通过参数覆盖本地端口，例如：mysql_tunnel_4090_start.bat 3307
if not "%~1"=="" set "LOCAL_PORT=%~1"

echo [INFO] 将本机 %LOCAL_PORT% -> %REMOTE_HOST%:3306 （经由 %JUMP_ALIAS%）建立隧道...

REM 检查端口是否已被占用
for /f "tokens=5" %%p in ('netstat -aon ^| findstr /r /c:":%LOCAL_PORT% .*LISTENING"') do (
  echo [ERROR] 本地端口 %LOCAL_PORT% 已被进程 PID=%%p 占用，请换端口（如 3307/3309）或先结束该进程：
  echo        taskkill /PID %%p /F
  pause
  exit /b 1
)

REM 启动 SSH 多跳隧道（使用 C:\Users\Administrator\.ssh\config 中的 JumpMachine 别名）
REM 显式写 xdx@192.168.1.123，避免与 4090_xdx_remote 的 ProxyCommand 冲突
start "mysql-tunnel-%LOCAL_PORT%" /MIN ^
  ssh -J %JUMP_ALIAS% %REMOTE_USER%@%REMOTE_HOST% ^
  -L 127.0.0.1:%LOCAL_PORT%:127.0.0.1:3306 -N ^
  -o ServerAliveInterval=60 -o ServerAliveCountMax=3 ^
  -o ExitOnForwardFailure=yes -o StrictHostKeyChecking=accept-new

echo [OK] 隧道进程已启动（新窗口，最小化）。如需输入密码，请切到该窗口按提示输入。
echo      Navicat 参数如下：
echo      主机: 127.0.0.1  端口: %LOCAL_PORT%  用户名: eav_user  密码: Eav_pass_1234  数据库: eav_db
echo.
echo [HINT] PowerShell 自检:  Test-NetConnection -ComputerName 127.0.0.1 -Port %LOCAL_PORT%
exit /b 0