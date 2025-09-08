#!/bin/bash

# 域名监控服务 - Linux智能部署脚本
# 支持初次部署和更新部署
# 使用方法: bash deploy.sh [选项]
#   无参数: 智能判断（已部署则更新，未部署则全新安装）
#   install: 强制全新安装
#   update: 仅更新代码和依赖
#   restart: 仅重启服务

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 部署模式
MODE=$1

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  域名监控服务 - 智能部署脚本${NC}"
echo -e "${GREEN}========================================${NC}"

# 检查是否在正确的目录
if [ ! -f "src/main.py" ]; then
    echo -e "${RED}错误: 请在项目根目录运行此脚本${NC}"
    exit 1
fi

# 获取当前目录
PROJECT_DIR=$(pwd)
echo -e "${YELLOW}项目目录: $PROJECT_DIR${NC}"

# 检测服务是否已安装
SERVICE_EXISTS=false
if systemctl list-unit-files | grep -q domain-monitor.service; then
    SERVICE_EXISTS=true
    echo -e "${BLUE}检测到已安装的服务${NC}"
fi

# 根据参数决定操作
if [ "$MODE" == "restart" ]; then
    echo -e "\n${YELLOW}重启服务...${NC}"
    sudo systemctl restart domain-monitor
    sudo systemctl status domain-monitor --no-pager
    echo -e "${GREEN}服务重启成功！${NC}"
    exit 0
fi

if [ "$MODE" == "update" ] || ([ "$SERVICE_EXISTS" == "true" ] && [ "$MODE" != "install" ]); then
    # 更新模式
    echo -e "\n${BLUE}========== 更新模式 ==========${NC}"
    
    # 1. 停止服务
    echo -e "\n${YELLOW}[1/4] 停止服务...${NC}"
    sudo systemctl stop domain-monitor
    echo -e "${GREEN}服务已停止${NC}"
    
    # 2. 更新依赖
    echo -e "\n${YELLOW}[2/4] 更新依赖...${NC}"
    if [ -d "venv" ]; then
        source venv/bin/activate
        python -m pip install --upgrade pip > /dev/null 2>&1
        python -m pip install -r requirements.txt --upgrade
        echo -e "${GREEN}依赖更新完成${NC}"
    else
        echo -e "${YELLOW}虚拟环境不存在，跳过依赖更新${NC}"
    fi
    
    # 3. 检查配置文件
    echo -e "\n${YELLOW}[3/4] 检查配置...${NC}"
    if [ ! -f "config.json" ]; then
        echo -e "${RED}警告: 配置文件不存在！${NC}"
        if [ -f "config_example.json" ]; then
            cp config_example.json config.json
            echo -e "${YELLOW}已复制示例配置，请编辑 config.json${NC}"
        fi
    else
        echo -e "${GREEN}配置文件正常${NC}"
    fi
    
    # 4. 重启服务
    echo -e "\n${YELLOW}[4/4] 重启服务...${NC}"
    sudo systemctl daemon-reload
    sudo systemctl start domain-monitor
    
    sleep 2
    if sudo systemctl is-active --quiet domain-monitor; then
        echo -e "${GREEN}✓ 服务更新成功！${NC}"
        echo -e "\n查看状态: ${YELLOW}sudo systemctl status domain-monitor${NC}"
    else
        echo -e "${RED}✗ 服务启动失败${NC}"
        sudo systemctl status domain-monitor --no-pager
    fi
    
else
    # 全新安装模式
    echo -e "\n${BLUE}========== 全新安装模式 ==========${NC}"
    
    # 1. 检查Python版本
    echo -e "\n${YELLOW}[1/7] 检查Python版本...${NC}"
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
    echo -e "\n${YELLOW}[2/7] 创建虚拟环境...${NC}"
    if [ ! -d "venv" ]; then
        $PYTHON_CMD -m venv venv
        echo -e "${GREEN}虚拟环境创建成功${NC}"
    else
        echo -e "${GREEN}虚拟环境已存在${NC}"
    fi
    
    # 3. 安装依赖
    echo -e "\n${YELLOW}[3/7] 安装依赖包...${NC}"
    source venv/bin/activate
    python -m pip install --upgrade pip > /dev/null 2>&1
    python -m pip install -r requirements.txt
    echo -e "${GREEN}依赖安装完成${NC}"
    
    # 4. 检查配置文件
    echo -e "\n${YELLOW}[4/7] 检查配置文件...${NC}"
    if [ ! -f "config.json" ]; then
        if [ -f "config_example.json" ]; then
            echo -e "${YELLOW}配置文件不存在，复制示例配置...${NC}"
            cp config_example.json config.json
            echo -e "${RED}请编辑 config.json 文件，填入你的 Bot Token 和 Chat ID${NC}"
            echo -e "${RED}编辑命令: nano config.json${NC}"
            echo -e "${YELLOW}配置完成后，重新运行: $0 ${NC}"
            exit 1
        else
            echo -e "${RED}配置文件和示例都不存在！${NC}"
            exit 1
        fi
    else
        echo -e "${GREEN}配置文件已存在${NC}"
    fi
    
    # 5. 创建systemd服务文件
    echo -e "\n${YELLOW}[5/7] 创建systemd服务...${NC}"
    
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
# 退出码3表示重启请求
SuccessExitStatus=3
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
    else
        echo -e "${RED}✗ 服务启动失败${NC}"
        echo -e "${YELLOW}查看错误信息:${NC}"
        sudo systemctl status domain-monitor --no-pager
        exit 1
    fi
fi

# 显示管理命令
echo -e "\n${BLUE}常用命令：${NC}"
echo -e "  更新代码后重新部署: ${YELLOW}./deploy.sh update${NC}"
echo -e "  仅重启服务: ${YELLOW}./deploy.sh restart${NC}"
echo -e "  查看服务状态: ${YELLOW}sudo systemctl status domain-monitor${NC}"
echo -e "  查看实时日志: ${YELLOW}sudo journalctl -u domain-monitor -f${NC}"
echo -e "  停止服务: ${YELLOW}sudo systemctl stop domain-monitor${NC}"
echo -e "  卸载服务: ${YELLOW}sudo systemctl disable domain-monitor${NC}"