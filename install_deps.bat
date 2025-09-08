@echo off
echo 安装域名监控系统依赖包...
echo.

echo [1/5] 安装基础依赖...
pip install httpx asyncio

echo.
echo [2/5] 安装HTTP/2支持（可选，提升性能）...
pip install httpx[http2]

echo.
echo [3/5] 安装系统监控（可选，自适应并发）...
pip install psutil

echo.
echo [4/5] 安装其他依赖...
pip install python-dateutil

echo.
echo [5/5] 显示已安装包...
pip list | findstr "httpx psutil h2"

echo.
echo 安装完成！
echo.
echo 注意：
echo - h2 包用于HTTP/2支持（可选）
echo - psutil 用于自适应并发控制（可选）
echo - 如果某些包安装失败，程序仍可运行，但部分功能会降级
echo.
pause