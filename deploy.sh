#!/bin/bash

# 域名监控服务 - Linux一键部署脚本
# 使用方法: bash deploy.sh

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  域名监控服务 - 一键部署${NC}"
echo -e "${GREEN}========================================${NC}"

# 检查是否在正确的目录
if [ ! -f "src/main.py" ]; then
    echo -e "${RED}错误: 请在项目根目录运行此脚本${NC}"
    exit 1
fi

# 获取当前目录
PROJECT_DIR=$(pwd)
echo -e "${YELLOW}项目目录: $PROJECT_DIR${NC}"

# 1. 检查Python版本
echo -e "\n${YELLOW}[1/6] 检查Python版本...${NC}"
if command -v python3 &> /dev/null; then
    PYTHON_CMD="python3"
elif command -v python &> /dev/null; then
    PYTHON_CMD="python"
else
    echo -e "${RED}Python未安装，请先安装Python 3.8+${NC}"
    exit 1
fi
$PYTHON_CMD --version

# 2. 创建虚拟环境
echo -e "\n${YELLOW}[2/6] 创建虚拟环境...${NC}"
if [ ! -d "venv" ]; then
    $PYTHON_CMD -m venv venv
    echo -e "${GREEN}虚拟环境创建成功${NC}"
else
    echo -e "${GREEN}虚拟环境已存在${NC}"
fi

# 3. 安装依赖
echo -e "\n${YELLOW}[3/6] 安装依赖包...${NC}"
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
echo -e "${GREEN}依赖安装完成${NC}"

# 4. 检查配置文件
echo -e "\n${YELLOW}[4/6] 检查配置文件...${NC}"
if [ ! -f "config.json" ]; then
    if [ -f "config_example.json" ]; then
        echo -e "${YELLOW}配置文件不存在，复制示例配置...${NC}"
        cp config_example.json config.json
        echo -e "${RED}请编辑 config.json 文件，填入你的 Bot Token 和 Chat ID${NC}"
        echo -e "${RED}编辑命令: nano config.json${NC}"
        exit 1
    else
        echo -e "${RED}配置文件和示例都不存在！${NC}"
        exit 1
    fi
else
    echo -e "${GREEN}配置文件已存在${NC}"
fi

# 5. 创建systemd服务文件
echo -e "\n${YELLOW}[5/6] 创建systemd服务...${NC}"

SERVICE_FILE="/tmp/domain-monitor.service"
cat > $SERVICE_FILE << EOF
[Unit]
Description=Domain Monitor Service
After=network.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
ExecStart=$PROJECT_DIR/venv/bin/python $PROJECT_DIR/src/main.py
Restart=always
RestartSec=10
StandardOutput=append:/var/log/domain-monitor.log
StandardError=append:/var/log/domain-monitor.log

[Install]
WantedBy=multi-user.target
EOF

# 复制到系统目录
sudo cp $SERVICE_FILE /etc/systemd/system/domain-monitor.service
sudo systemctl daemon-reload
echo -e "${GREEN}Systemd服务创建成功${NC}"

# 6. 配置日志轮转
echo -e "\n${YELLOW}[6/7] 配置日志轮转...${NC}"
LOGROTATE_FILE="/etc/logrotate.d/domain-monitor"
sudo tee $LOGROTATE_FILE > /dev/null << EOF
/var/log/domain-monitor.log {
    daily
    rotate 7
    maxsize 100M
    compress
    delaycompress
    missingok
    notifempty
    create 644 $USER $USER
    postrotate
        systemctl reload domain-monitor > /dev/null 2>&1 || true
    endscript
}
EOF
echo -e "${GREEN}日志轮转配置成功（每日轮转，保留7天）${NC}"

# 7. 启动服务
echo -e "\n${YELLOW}[7/7] 启动服务...${NC}"
sudo systemctl enable domain-monitor
sudo systemctl restart domain-monitor

# 检查服务状态
sleep 2
if sudo systemctl is-active --quiet domain-monitor; then
    echo -e "${GREEN}✓ 服务启动成功！${NC}"
    echo -e "\n${GREEN}========================================${NC}"
    echo -e "${GREEN}  部署完成！${NC}"
    echo -e "${GREEN}========================================${NC}"
    echo -e "\n常用命令:"
    echo -e "  查看状态: ${YELLOW}sudo systemctl status domain-monitor${NC}"
    echo -e "  查看日志: ${YELLOW}sudo journalctl -u domain-monitor -f${NC}"
    echo -e "  停止服务: ${YELLOW}sudo systemctl stop domain-monitor${NC}"
    echo -e "  重启服务: ${YELLOW}sudo systemctl restart domain-monitor${NC}"
else
    echo -e "${RED}✗ 服务启动失败${NC}"
    echo -e "${YELLOW}查看错误信息:${NC}"
    sudo systemctl status domain-monitor --no-pager
    exit 1
fi