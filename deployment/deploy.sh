#!/bin/bash

# 域名监控服务部署脚本
# 支持多种部署方式

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 配置变量
APP_NAME="domain-monitor"
APP_DIR="/opt/domain-monitor"
SERVICE_USER="monitor"
PYTHON_VERSION="python3"

# 打印带颜色的消息
print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_info() {
    echo -e "${YELLOW}→ $1${NC}"
}

# 检查系统要求
check_requirements() {
    print_info "检查系统要求..."
    
    # 检查Python
    if ! command -v $PYTHON_VERSION &> /dev/null; then
        print_error "Python3 未安装"
        exit 1
    fi
    
    # 检查pip (优先pip3，fallback到pip)
    if command -v pip3 &> /dev/null; then
        PIP_CMD="pip3"
    elif command -v pip &> /dev/null; then
        PIP_CMD="pip"
    else
        print_error "pip 未安装"
        exit 1
    fi
    print_info "使用 $PIP_CMD"
    
    print_success "系统要求满足"
}

# 创建用户
create_user() {
    print_info "创建服务用户..."
    
    if id "$SERVICE_USER" &>/dev/null; then
        print_info "用户 $SERVICE_USER 已存在"
    else
        sudo useradd -m -s /bin/bash $SERVICE_USER
        print_success "用户 $SERVICE_USER 创建成功"
    fi
}

# 安装应用
install_app() {
    print_info "安装应用..."
    
    # 创建应用目录
    sudo mkdir -p $APP_DIR
    sudo cp -r ./* $APP_DIR/
    
    # 创建虚拟环境
    cd $APP_DIR
    sudo -u $SERVICE_USER $PYTHON_VERSION -m venv venv
    
    # 安装依赖
    sudo -u $SERVICE_USER ./venv/bin/pip install --upgrade pip
    sudo -u $SERVICE_USER ./venv/bin/pip install -r requirements.txt
    
    # 设置权限
    sudo chown -R $SERVICE_USER:$SERVICE_USER $APP_DIR
    
    print_success "应用安装完成"
}

# systemd 部署
deploy_systemd() {
    print_info "配置 systemd 服务..."
    
    # 复制服务文件
    sudo cp domain-monitor.service /etc/systemd/system/
    
    # 创建日志目录
    sudo mkdir -p /var/log/domain-monitor
    sudo chown $SERVICE_USER:$SERVICE_USER /var/log/domain-monitor
    
    # 重载systemd
    sudo systemctl daemon-reload
    
    # 启用并启动服务
    sudo systemctl enable domain-monitor
    sudo systemctl start domain-monitor
    
    print_success "systemd 服务配置完成"
    
    # 显示服务状态
    sudo systemctl status domain-monitor --no-pager
}

# Docker 部署
deploy_docker() {
    print_info "使用 Docker 部署..."
    
    if ! command -v docker &> /dev/null; then
        print_error "Docker 未安装"
        exit 1
    fi
    
    # 构建镜像
    docker build -t $APP_NAME .
    
    # 运行容器
    docker-compose up -d
    
    print_success "Docker 部署完成"
    
    # 显示容器状态
    docker ps | grep $APP_NAME
}

# PM2 部署
deploy_pm2() {
    print_info "使用 PM2 部署..."
    
    if ! command -v pm2 &> /dev/null; then
        print_error "PM2 未安装，请先安装: npm install -g pm2"
        exit 1
    fi
    
    cd $APP_DIR
    
    # 启动应用
    pm2 start ecosystem.config.js
    
    # 保存PM2配置
    pm2 save
    
    # 设置开机启动
    pm2 startup systemd -u $SERVICE_USER --hp /home/$SERVICE_USER
    
    print_success "PM2 部署完成"
    
    # 显示应用状态
    pm2 status
}

# 显示帮助
show_help() {
    echo "域名监控服务部署脚本"
    echo ""
    echo "用法: $0 [选项]"
    echo ""
    echo "选项:"
    echo "  systemd   - 使用 systemd 部署 (Linux 推荐)"
    echo "  docker    - 使用 Docker 部署"
    echo "  pm2       - 使用 PM2 部署"
    echo "  help      - 显示此帮助信息"
    echo ""
    echo "示例:"
    echo "  $0 systemd"
}

# 主函数
main() {
    case "$1" in
        systemd)
            check_requirements
            create_user
            install_app
            deploy_systemd
            ;;
        docker)
            deploy_docker
            ;;
        pm2)
            check_requirements
            create_user
            install_app
            deploy_pm2
            ;;
        help|--help|-h)
            show_help
            ;;
        *)
            print_error "无效的选项: $1"
            echo ""
            show_help
            exit 1
            ;;
    esac
}

# 执行主函数
main "$@"