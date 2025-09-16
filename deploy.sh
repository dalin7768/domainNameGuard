#!/bin/bash

# 域名监控服务 - Linux部署脚本
# 支持按名称部署和管理多个服务实例
# 使用方法: bash deploy.sh [选项] [实例名称]
#   deploy NAME: 部署名为NAME的实例 (如: deploy.sh deploy client1)
#   start NAME: 启动指定实例 (如: deploy.sh start client1)
#   stop NAME: 停止指定实例 (如: deploy.sh stop client1)
#   restart NAME: 重启指定实例 (如: deploy.sh restart client1)
#   status [NAME]: 查看所有或指定实例状态
#   update [NAME]: 更新所有或指定实例
#   remove NAME: 删除指定实例
#
#   使用 -all 后缀对所有实例执行操作:
#   start-all, stop-all, update-all, remove-all

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 参数
ACTION=$1
INSTANCE_NAME=$2

echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}  域名监控服务 - 部署脚本${NC}"
echo -e "${GREEN}========================================${NC}"

# 检查是否在正确的目录
if [ ! -f "src/main.py" ]; then
    echo -e "${RED}错误: 请在项目根目录运行此脚本${NC}"
    exit 1
fi

# 获取当前目录
PROJECT_DIR=$(pwd)
echo -e "${YELLOW}项目目录: $PROJECT_DIR${NC}"

# 显示使用帮助
show_help() {
    echo -e "\n${BLUE}使用方法:${NC}"
    echo -e "  ${YELLOW}部署实例:${NC} $0 deploy NAME"
    echo -e "  ${YELLOW}启动实例:${NC} $0 start NAME"
    echo -e "  ${YELLOW}停止实例:${NC} $0 stop NAME"
    echo -e "  ${YELLOW}重启实例:${NC} $0 restart NAME"
    echo -e "  ${YELLOW}查看状态:${NC} $0 status [NAME]"
    echo -e "  ${YELLOW}更新实例:${NC} $0 update [NAME]"
    echo -e "  ${YELLOW}删除实例:${NC} $0 remove NAME"
    echo -e "  ${YELLOW}批量操作:${NC} $0 start-all | stop-all | update-all | remove-all"
    echo -e "\n${BLUE}示例:${NC}"
    echo -e "  $0 deploy client1      # 部署名为 client1 的实例"
    echo -e "  $0 start client1       # 启动 client1 实例"
    echo -e "  $0 status              # 查看所有实例状态"
    echo -e "  $0 status client1      # 查看 client1 实例状态"
    echo -e "  $0 stop-all            # 停止所有实例"
}

# 获取服务名称
get_service_name() {
    local name=$1
    echo "domain-monitor-${name}"
}

# 获取配置文件名
get_config_file() {
    local name=$1
    echo "config-${name}.json"
}

# 获取日志文件名
get_log_file() {
    local name=$1
    echo "/var/log/domain-monitor-${name}.log"
}

# 检查实例是否存在
check_instance_exists() {
    local name=$1
    local service_name=$(get_service_name $name)
    systemctl list-unit-files | grep -q "${service_name}.service"
}

# 验证实例名称
validate_instance_name() {
    local name=$1
    if [[ -z "$name" ]]; then
        echo -e "${RED}错误: 请提供实例名称${NC}"
        return 1
    fi

    # 检查名称是否包含有效字符（字母、数字、连字符、下划线）
    if [[ ! "$name" =~ ^[a-zA-Z0-9_-]+$ ]]; then
        echo -e "${RED}错误: 实例名称只能包含字母、数字、连字符和下划线${NC}"
        return 1
    fi

    return 0
}

# 创建单个实例
create_instance() {
    local name=$1
    local service_name=$(get_service_name $name)
    local config_file=$(get_config_file $name)
    local log_file=$(get_log_file $name)

    # 验证实例名称
    if ! validate_instance_name "$name"; then
        return 1
    fi

    echo -e "\n${YELLOW}创建实例 ${name}...${NC}"

    # 1. 创建配置文件
    if [ ! -f "$config_file" ]; then
        if [ -f "config_example.json" ]; then
            cp config_example.json "$config_file"
            echo -e "${GREEN}已创建配置文件: $config_file${NC}"
            echo -e "${RED}请编辑 $config_file 并配置不同的参数${NC}"
        else
            echo -e "${RED}配置文件模板不存在！${NC}"
            return 1
        fi
    fi

    # 2. 创建systemd服务文件
    SERVICE_FILE="/tmp/${service_name}.service"
    cat > $SERVICE_FILE << EOF
[Unit]
Description=Domain Monitor Service Instance ${name}
After=network.target

[Service]
Type=simple
User=$USER
Group=$USER
WorkingDirectory=$PROJECT_DIR
Environment="PATH=$PROJECT_DIR/venv/bin"
Environment="CONFIG_FILE=$config_file"
ExecStart=$PROJECT_DIR/venv/bin/python $PROJECT_DIR/src/main.py --config=$config_file
Restart=on-failure
RestartSec=10
# 退出码0表示正常停止，不重启
# 退出码3表示程序请求重启，允许重启
RestartPreventExitStatus=0
SuccessExitStatus=0 3
StandardOutput=append:$log_file
StandardError=append:$log_file

[Install]
WantedBy=multi-user.target
EOF

    # 复制到系统目录
    sudo cp $SERVICE_FILE /etc/systemd/system/${service_name}.service
    sudo systemctl daemon-reload

    # 3. 配置日志轮转
    LOGROTATE_FILE="/etc/logrotate.d/${service_name}"
    sudo tee $LOGROTATE_FILE > /dev/null << EOF
$log_file {
    daily
    rotate 3
    maxsize 50M
    compress
    delaycompress
    missingok
    notifempty
    create 644 $USER $USER
    copytruncate
}
EOF

    echo -e "${GREEN}实例 ${name} 创建完成${NC}"
}

# 启动实例
start_instance() {
    local name=$1
    local service_name=$(get_service_name $name)

    if ! validate_instance_name "$name"; then
        return 1
    fi

    if ! check_instance_exists $name; then
        echo -e "${RED}实例 ${name} 不存在${NC}"
        return 1
    fi

    echo -e "\n${YELLOW}启动实例 ${name}..${NC}"
    sudo systemctl enable $service_name
    sudo systemctl start $service_name

    sleep 2
    if sudo systemctl is-active --quiet $service_name; then
        echo -e "${GREEN}✓ 实例 ${name} 启动成功${NC}"
    else
        echo -e "${RED}✗ 实例 ${name} 启动失败${NC}"
        sudo systemctl status $service_name --no-pager
        return 1
    fi
}

# 停止实例
stop_instance() {
    local name=$1
    local service_name=$(get_service_name $name)

    if ! validate_instance_name "$name"; then
        return 1
    fi

    if ! check_instance_exists $name; then
        echo -e "${RED}实例 ${name} 不存在${NC}"
        return 1
    fi

    echo -e "\n${YELLOW}停止实例 ${name}...${NC}"

    # 先禁用自动重启，然后停止服务
    sudo systemctl stop $service_name

    # 等待服务完全停止
    sleep 2

    if sudo systemctl is-active --quiet $service_name; then
        echo -e "${RED}✗ 实例 ${name} 停止失败，强制停止${NC}"
        sudo systemctl kill $service_name
        sleep 1
    fi

    if sudo systemctl is-active --quiet $service_name; then
        echo -e "${RED}✗ 实例 ${name} 无法停止${NC}"
        sudo systemctl status $service_name --no-pager
        return 1
    else
        echo -e "${GREEN}✓ 实例 ${name} 已停止${NC}"
    fi
}

# 重启实例
restart_instance() {
    local name=$1
    local service_name=$(get_service_name $name)

    if ! validate_instance_name "$name"; then
        return 1
    fi

    if ! check_instance_exists $name; then
        echo -e "${RED}实例 ${name} 不存在${NC}"
        return 1
    fi

    echo -e "\n${YELLOW}重启实例 ${name}...${NC}"

    # 使用 systemctl restart 直接重启
    sudo systemctl restart $service_name

    # 检查重启结果
    sleep 2
    if sudo systemctl is-active --quiet $service_name; then
        echo -e "${GREEN}✓ 实例 ${name} 重启成功${NC}"
    else
        echo -e "${RED}✗ 实例 ${name} 重启失败${NC}"
        sudo systemctl status $service_name --no-pager
        return 1
    fi
}

# 查看实例状态
show_status() {
    local name=$1

    if [ -n "$name" ]; then
        # 查看指定实例
        if ! validate_instance_name "$name"; then
            return 1
        fi

        if check_instance_exists $name; then
            local service_name=$(get_service_name $name)
            echo -e "\n${BLUE}实例 ${name} 状态:${NC}"
            sudo systemctl status $service_name --no-pager
        else
            echo -e "${RED}实例 ${name} 不存在${NC}"
        fi
    else
        # 查看所有实例
        echo -e "\n${BLUE}所有实例状态:${NC}"
        for service_file in /etc/systemd/system/domain-monitor-*.service; do
            if [ -f "$service_file" ]; then
                service_name=$(basename "$service_file" .service)
                instance_name=${service_name#domain-monitor-}

                if sudo systemctl is-active --quiet $service_name; then
                    status="${GREEN}运行中${NC}"
                else
                    status="${RED}已停止${NC}"
                fi

                echo -e "  实例 ${instance_name}: $status"
            fi
        done
    fi
}

# 更新实例
update_instance() {
    local name=$1

    if [ -n "$name" ]; then
        # 更新指定实例
        if ! validate_instance_name "$name"; then
            return 1
        fi

        if check_instance_exists $name; then
            echo -e "\n${YELLOW}更新实例 ${name}...${NC}"
            stop_instance $name
            start_instance $name
        else
            echo -e "${RED}实例 ${name} 不存在${NC}"
        fi
    else
        # 更新所有实例
        echo -e "\n${YELLOW}更新所有实例...${NC}"
        for service_file in /etc/systemd/system/domain-monitor-*.service; do
            if [ -f "$service_file" ]; then
                service_name=$(basename "$service_file" .service)
                instance_name=${service_name#domain-monitor-}
                echo -e "更新实例 ${instance_name}..."
                restart_instance $instance_name
            fi
        done
    fi
}

# 删除实例
remove_instance() {
    local name=$1
    local service_name=$(get_service_name $name)
    local config_file=$(get_config_file $name)

    if ! validate_instance_name "$name"; then
        return 1
    fi

    if ! check_instance_exists $name; then
        echo -e "${RED}实例 ${name} 不存在${NC}"
        return 1
    fi

    echo -e "\n${YELLOW}删除实例 ${name}...${NC}"

    # 停止服务
    sudo systemctl stop $service_name 2>/dev/null || true
    sudo systemctl disable $service_name 2>/dev/null || true

    # 删除服务文件
    sudo rm -f /etc/systemd/system/${service_name}.service
    sudo rm -f /etc/logrotate.d/${service_name}

    # 重载systemd
    sudo systemctl daemon-reload

    echo -e "${GREEN}实例 ${name} 已删除${NC}"
    echo -e "${YELLOW}注意: 配置文件 $config_file 和日志文件未删除${NC}"
}

# 检查环境和依赖
check_environment() {
    echo -e "\n${YELLOW}检查环境...${NC}"

    # 检查Python
    if command -v python3 &> /dev/null; then
        PYTHON_CMD="python3"
    elif command -v python &> /dev/null; then
        PYTHON_CMD="python"
    else
        echo -e "${RED}Python未安装，请先安装Python 3.8+${NC}"
        exit 1
    fi

    # 检查虚拟环境
    if [ ! -d "venv" ]; then
        echo -e "${YELLOW}创建虚拟环境...${NC}"
        $PYTHON_CMD -m venv venv
    fi

    # 安装依赖
    echo -e "${YELLOW}更新依赖...${NC}"
    source venv/bin/activate
    python -m pip install --upgrade pip > /dev/null 2>&1
    python -m pip install -r requirements.txt --upgrade
    echo -e "${GREEN}环境检查完成${NC}"
}

# 主逻辑
case "$ACTION" in
    "deploy")
        if [ -z "$INSTANCE_NAME" ]; then
            echo -e "${RED}请指定要部署的实例名称${NC}"
            show_help
            exit 1
        fi

        check_environment

        echo -e "\n${BLUE}部署实例 ${INSTANCE_NAME}...${NC}"
        create_instance $INSTANCE_NAME
        start_instance $INSTANCE_NAME

        echo -e "\n${GREEN}========================================${NC}"
        echo -e "${GREEN}  实例 ${INSTANCE_NAME} 部署完成！${NC}"
        echo -e "${GREEN}========================================${NC}"
        show_status $INSTANCE_NAME
        ;;

    "start")
        if [ -z "$INSTANCE_NAME" ]; then
            echo -e "${RED}请指定实例名称${NC}"
            exit 1
        fi
        start_instance $INSTANCE_NAME
        ;;

    "stop")
        if [ -z "$INSTANCE_NAME" ]; then
            echo -e "${RED}请指定实例名称${NC}"
            exit 1
        fi
        stop_instance $INSTANCE_NAME
        ;;

    "restart")
        if [ -z "$INSTANCE_NAME" ]; then
            echo -e "${RED}请指定实例名称${NC}"
            exit 1
        fi
        restart_instance $INSTANCE_NAME
        ;;

    "status")
        show_status $INSTANCE_NAME
        ;;

    "update")
        # 先更新代码和依赖
        check_environment
        update_instance $INSTANCE_NAME
        ;;

    "remove")
        if [ -z "$INSTANCE_NAME" ]; then
            echo -e "${RED}请指定实例名称${NC}"
            exit 1
        fi
        remove_instance $INSTANCE_NAME
        ;;

    "start-all")
        echo -e "\n${YELLOW}启动所有实例...${NC}"
        for service_file in /etc/systemd/system/domain-monitor-*.service; do
            if [ -f "$service_file" ]; then
                service_name=$(basename "$service_file" .service)
                instance_name=${service_name#domain-monitor-}
                start_instance $instance_name
            fi
        done
        ;;

    "stop-all")
        echo -e "\n${YELLOW}停止所有实例...${NC}"
        for service_file in /etc/systemd/system/domain-monitor-*.service; do
            if [ -f "$service_file" ]; then
                service_name=$(basename "$service_file" .service)
                instance_name=${service_name#domain-monitor-}
                stop_instance $instance_name
            fi
        done
        ;;

    "update-all")
        echo -e "\n${YELLOW}更新所有实例...${NC}"
        check_environment
        for service_file in /etc/systemd/system/domain-monitor-*.service; do
            if [ -f "$service_file" ]; then
                service_name=$(basename "$service_file" .service)
                instance_name=${service_name#domain-monitor-}
                restart_instance $instance_name
            fi
        done
        ;;

    "remove-all")
        echo -e "\n${YELLOW}删除所有实例...${NC}"
        echo -e "${RED}警告: 这将删除所有实例！${NC}"
        read -p "是否继续? (y/N): " confirm
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
            for service_file in /etc/systemd/system/domain-monitor-*.service; do
                if [ -f "$service_file" ]; then
                    service_name=$(basename "$service_file" .service)
                    instance_name=${service_name#domain-monitor-}
                    remove_instance $instance_name
                fi
            done
        else
            echo -e "${YELLOW}操作已取消${NC}"
        fi
        ;;

    *)
        echo -e "${RED}未知操作: $ACTION${NC}"
        show_help
        exit 1
        ;;
esac

# 显示管理命令提示
if [ "$ACTION" == "deploy" ]; then
    echo -e "\n${BLUE}常用命令：${NC}"
    echo -e "  查看所有实例状态: ${YELLOW}$0 status${NC}"
    echo -e "  查看指定实例状态: ${YELLOW}$0 status ${INSTANCE_NAME}${NC}"
    echo -e "  重启指定实例: ${YELLOW}$0 restart ${INSTANCE_NAME}${NC}"
    echo -e "  更新所有实例: ${YELLOW}$0 update-all${NC}"
    echo -e "  停止所有实例: ${YELLOW}$0 stop-all${NC}"
    echo -e "  启动所有实例: ${YELLOW}$0 start-all${NC}"
    echo -e "\n${BLUE}日志文件：${NC}"
    log_file=$(get_log_file $INSTANCE_NAME)
    echo -e "  实例 ${INSTANCE_NAME}: ${YELLOW}tail -f $log_file${NC}"
fi