@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo ========================================
echo   域名监控服务 - Windows一键部署
echo ========================================
echo.

REM 检查是否在正确的目录
if not exist "src\main.py" (
    echo [错误] 请在项目根目录运行此脚本
    pause
    exit /b 1
)

REM 获取当前目录
set PROJECT_DIR=%cd%
echo [信息] 项目目录: %PROJECT_DIR%
echo.

REM 1. 检查Python是否安装
echo [1/5] 检查Python环境...
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] Python未安装或未添加到PATH
    echo 请先安装Python 3.8或更高版本
    echo 下载地址: https://www.python.org/downloads/
    pause
    exit /b 1
)
python --version
echo [成功] Python环境检查通过
echo.

REM 2. 创建虚拟环境
echo [2/5] 创建虚拟环境...
if not exist "venv" (
    python -m venv venv
    if %errorlevel% neq 0 (
        echo [错误] 虚拟环境创建失败
        pause
        exit /b 1
    )
    echo [成功] 虚拟环境创建成功
) else (
    echo [信息] 虚拟环境已存在
)
echo.

REM 3. 安装依赖
echo [3/5] 安装依赖包...
call venv\Scripts\activate.bat
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [错误] 依赖安装失败
    pause
    exit /b 1
)
echo [成功] 依赖安装完成
echo.

REM 4. 检查配置文件
echo [4/5] 检查配置文件...
if not exist "config.json" (
    if exist "config_example.json" (
        echo [信息] 配置文件不存在，复制示例配置...
        copy config_example.json config.json >nul
        echo.
        echo [警告] 请编辑 config.json 文件：
        echo   1. 填入你的 Bot Token
        echo   2. 填入你的 Chat ID
        echo.
        echo 是否现在打开配置文件？(Y/N)
        set /p open_config=
        if /i "!open_config!"=="Y" (
            notepad config.json
            echo.
            echo 配置完成后，按任意键继续...
            pause >nul
        ) else (
            echo [警告] 请手动编辑 config.json 后重新运行部署脚本
            pause
            exit /b 1
        )
    ) else (
        echo [错误] 配置文件和示例都不存在！
        pause
        exit /b 1
    )
) else (
    echo [信息] 配置文件已存在
)
echo.

REM 5. 创建启动脚本
echo [5/5] 创建启动脚本...
echo @echo off > start.bat
echo title Domain Monitor >> start.bat
echo cd /d "%PROJECT_DIR%" >> start.bat
echo call venv\Scripts\activate.bat >> start.bat
echo python src\main.py >> start.bat
echo pause >> start.bat
echo [成功] 启动脚本创建成功
echo.

REM 创建Windows任务计划（可选）
echo ========================================
echo   部署完成！
echo ========================================
echo.
echo 是否设置开机自启动？(Y/N)
set /p auto_start=
if /i "!auto_start!"=="Y" (
    echo.
    echo 正在创建开机启动任务...
    schtasks /create /tn "DomainMonitor" /tr "\"%PROJECT_DIR%\start.bat\"" /sc onstart /ru "%USERNAME%" /f >nul 2>&1
    if !errorlevel! equ 0 (
        echo [成功] 开机自启动设置成功
    ) else (
        echo [警告] 自启动设置失败，请手动设置
        echo 可以将 start.bat 添加到启动文件夹：
        echo Win+R 输入 shell:startup 打开启动文件夹
    )
)
echo.

REM 询问是否立即启动
echo 是否立即启动服务？(Y/N)
set /p start_now=
if /i "!start_now!"=="Y" (
    echo.
    echo 正在启动服务...
    start "Domain Monitor" start.bat
    echo [成功] 服务已在新窗口启动
) else (
    echo.
    echo 稍后可以运行 start.bat 启动服务
)

echo.
echo ========================================
echo   使用说明
echo ========================================
echo.
echo 启动服务: 双击 start.bat
echo 停止服务: 在运行窗口按 Ctrl+C
echo 查看日志: 查看 domain_monitor.log
echo 修改配置: 编辑 config.json
echo.
echo 部署完成！
pause