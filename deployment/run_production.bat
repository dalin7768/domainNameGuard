@echo off
echo ========================================
echo   域名监控服务 - Windows生产环境启动
echo ========================================
echo.

REM 检查Python是否安装
python --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] Python未安装或未添加到PATH
    echo 请先安装Python 3.8或更高版本
    pause
    exit /b 1
)

REM 创建虚拟环境（如果不存在）
if not exist "venv" (
    echo [信息] 创建虚拟环境...
    python -m venv venv
)

REM 激活虚拟环境
echo [信息] 激活虚拟环境...
call venv\Scripts\activate.bat

REM 升级pip
echo [信息] 升级pip...
python -m pip install --upgrade pip

REM 安装/更新依赖
echo [信息] 安装依赖包...
pip install -r requirements.txt

REM 检查配置文件
if not exist "config.json" (
    echo [错误] 配置文件 config.json 不存在
    echo 请先创建并配置 config.json 文件
    pause
    exit /b 1
)

REM 创建日志目录
if not exist "logs" (
    mkdir logs
)

echo.
echo [信息] 启动域名监控服务...
echo ========================================
echo.

REM 启动服务
python src\main.py

REM 如果程序意外退出，暂停以查看错误
if %errorlevel% neq 0 (
    echo.
    echo [错误] 程序异常退出，错误代码: %errorlevel%
    pause
)