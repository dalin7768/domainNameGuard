@echo off
echo ========================================
echo   日志清理工具
echo ========================================
echo.

REM 设置日志目录和文件
set LOG_DIR=%~dp0..
set LOG_FILE=%LOG_DIR%\domain_monitor.log
set MAX_SIZE=104857600
REM 100MB = 104857600 bytes

REM 检查日志文件是否存在
if not exist "%LOG_FILE%" (
    echo [信息] 日志文件不存在
    pause
    exit /b 0
)

REM 获取文件大小
for %%A in ("%LOG_FILE%") do set FILE_SIZE=%%~zA
echo [信息] 当前日志大小: %FILE_SIZE% bytes

REM 如果超过最大大小，进行轮转
if %FILE_SIZE% GTR %MAX_SIZE% (
    echo [信息] 日志文件超过100MB，开始轮转...
    
    REM 删除最旧的备份
    if exist "%LOG_FILE%.7" del "%LOG_FILE%.7"
    
    REM 轮转备份文件
    for /L %%i in (6,-1,1) do (
        set /a next=%%i+1
        if exist "%LOG_FILE%.%%i" (
            move "%LOG_FILE%.%%i" "%LOG_FILE%.!next!" >nul 2>&1
        )
    )
    
    REM 备份当前日志
    move "%LOG_FILE%" "%LOG_FILE%.1" >nul 2>&1
    
    REM 创建新的日志文件
    echo Log rotated at %date% %time% > "%LOG_FILE%"
    
    echo [成功] 日志轮转完成
) else (
    echo [信息] 日志文件未超过限制，无需清理
)

echo.
echo 按任意键退出...
pause >nul