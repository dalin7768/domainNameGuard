# 部署指南

本目录包含各种生产环境部署方案的配置文件和脚本。

## 🚀 快速部署

### Linux (推荐)
```bash
chmod +x deploy.sh
sudo ./deploy.sh systemd
```

### Docker
```bash
docker-compose up -d
```

### Windows
```batch
run_production.bat
```

## 📁 文件说明

| 文件 | 用途 | 平台 |
|------|------|------|
| `deploy.sh` | 一键部署脚本 | Linux |
| `domain-monitor.service` | systemd 服务配置 | Linux |
| `docker-compose.yml` | Docker Compose 配置 | 跨平台 |
| `Dockerfile` | Docker 镜像构建 | 跨平台 |
| `ecosystem.config.js` | PM2 进程管理配置 | Node.js |
| `run_production.bat` | Windows 启动脚本 | Windows |
| `install_windows_service.py` | Windows 服务安装 | Windows |

## 🐧 Linux 部署 (systemd)

### 自动部署
```bash
# 使用部署脚本
chmod +x deploy.sh
sudo ./deploy.sh systemd
```

### 手动部署
```bash
# 1. 创建服务用户
sudo useradd -m -s /bin/bash monitor

# 2. 复制文件
sudo cp -r /path/to/project /opt/domain-monitor
sudo chown -R monitor:monitor /opt/domain-monitor

# 3. 安装依赖
cd /opt/domain-monitor
sudo -u monitor python3 -m venv venv
sudo -u monitor ./venv/bin/pip install -r requirements.txt

# 4. 安装服务
sudo cp deployment/domain-monitor.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable domain-monitor
sudo systemctl start domain-monitor

# 5. 查看状态
sudo systemctl status domain-monitor
sudo journalctl -u domain-monitor -f
```

### 服务管理
```bash
# 启动服务
sudo systemctl start domain-monitor

# 停止服务
sudo systemctl stop domain-monitor

# 重启服务
sudo systemctl restart domain-monitor

# 查看日志
sudo journalctl -u domain-monitor -f

# 禁用开机启动
sudo systemctl disable domain-monitor
```

## 🐳 Docker 部署

### 基础部署
```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止服务
docker-compose down

# 重启服务
docker-compose restart
```

### 自定义配置
```yaml
# docker-compose.override.yml
version: '3.8'
services:
  domain-monitor:
    environment:
      - TZ=Asia/Shanghai
    volumes:
      - ./custom-config.json:/app/config.json
    restart: always
```

### 构建镜像
```bash
# 构建本地镜像
docker build -t domain-monitor:latest .

# 推送到仓库
docker tag domain-monitor:latest your-registry/domain-monitor:latest
docker push your-registry/domain-monitor:latest
```

## 🪟 Windows 部署

### 方式1：批处理脚本
```batch
# 直接运行
run_production.bat
```

### 方式2：Windows 服务

#### 安装服务
```batch
# 管理员权限运行
python install_windows_service.py install
python install_windows_service.py start
```

#### 服务管理
```batch
# 停止服务
python install_windows_service.py stop

# 重启服务
python install_windows_service.py restart

# 卸载服务
python install_windows_service.py remove
```

#### 使用 NSSM（推荐）
```batch
# 下载 NSSM: https://nssm.cc/download
nssm install DomainMonitor "C:\Python39\python.exe" "C:\path\to\main.py"
nssm set DomainMonitor AppDirectory "C:\path\to\project"
nssm set DomainMonitor DisplayName "Domain Monitor Service"
nssm set DomainMonitor Description "监控域名可用性的服务"
nssm start DomainMonitor
```

### 方式3：任务计划程序
1. 打开"任务计划程序"
2. 创建基本任务
3. 触发器：计算机启动时
4. 操作：启动程序
5. 程序：`python.exe`
6. 参数：`main.py`
7. 起始位置：项目目录

## 🔄 PM2 部署 (Node.js)

### 安装 PM2
```bash
npm install -g pm2
```

### 启动服务
```bash
# 使用配置文件
pm2 start ecosystem.config.js

# 或直接启动
pm2 start main.py --name domain-monitor --interpreter python3
```

### 管理服务
```bash
# 查看状态
pm2 status

# 查看日志
pm2 logs domain-monitor

# 重启
pm2 restart domain-monitor

# 停止
pm2 stop domain-monitor

# 删除
pm2 delete domain-monitor
```

### 开机启动
```bash
# 保存当前进程列表
pm2 save

# 生成启动脚本
pm2 startup

# 按提示执行命令
```

## 🔒 安全建议

### 1. 用户权限
- 创建专用用户运行服务
- 避免使用 root/Administrator
- 限制文件访问权限

### 2. 网络安全
- 使用防火墙限制出站连接
- 仅允许访问 Telegram API
- 配置 HTTPS 代理（如需）

### 3. 配置保护
```bash
# Linux
chmod 600 config.json
chown monitor:monitor config.json

# 使用环境变量
export BOT_TOKEN="your_token"
export CHAT_ID="your_chat_id"
```

### 4. 日志管理
```bash
# 日志轮转 (Linux)
cat > /etc/logrotate.d/domain-monitor << EOF
/opt/domain-monitor/logs/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 monitor monitor
}
EOF
```

## 📊 监控建议

### 1. 进程监控
```bash
# 使用 systemd (Linux)
systemctl status domain-monitor

# 使用 PM2
pm2 monit

# 使用 Docker
docker ps
docker stats
```

### 2. 资源监控
- CPU 使用率 < 80%
- 内存使用 < 1GB
- 磁盘空间（日志）
- 网络连接数

### 3. 应用监控
- 检查完成时间
- 域名成功率
- Telegram 消息发送
- 错误日志

### 4. 告警设置
```bash
# 使用 systemd
OnFailure=notify-email@%i.service

# 使用 PM2
pm2 set pm2:alert-email your@email.com

# 使用 Docker
docker run -d \
  --name watchtower \
  --restart always \
  -v /var/run/docker.sock:/var/run/docker.sock \
  containrrr/watchtower \
  --notification-email-server smtp.gmail.com
```

## 🔧 故障排查

### 服务无法启动
1. 检查 Python 版本（需要 3.8+）
2. 验证依赖安装完整
3. 确认配置文件存在且格式正确
4. 查看错误日志

### 内存占用过高
1. 减少 max_concurrent 配置
2. 检查域名列表大小
3. 启用自适应并发控制
4. 定期重启服务

### 网络连接问题
1. 检查防火墙规则
2. 验证 DNS 解析
3. 测试 Telegram API 连接
4. 配置代理（如需）

## 📋 部署检查清单

- [ ] Python 3.8+ 已安装
- [ ] 依赖包已安装
- [ ] config.json 已配置
- [ ] Bot Token 有效
- [ ] Chat ID 正确
- [ ] 机器人已加入群组
- [ ] 网络可访问 Telegram
- [ ] 日志目录可写
- [ ] 服务自动启动已配置
- [ ] 监控告警已设置

## 🆘 常见问题

### Q: 选择哪种部署方式？
A: 
- Linux 服务器：systemd（最稳定）
- 容器环境：Docker（最便携）
- Windows 服务器：Windows 服务
- 已有 Node.js：PM2（功能最全）

### Q: 如何更新服务？
A:
1. 备份配置文件
2. 拉取最新代码
3. 安装新依赖
4. 重启服务

### Q: 如何实现高可用？
A:
1. 使用负载均衡
2. 多实例部署（不同服务器）
3. 配置健康检查
4. 自动故障转移

### Q: 如何备份和恢复？
A:
```bash
# 备份
tar -czf backup-$(date +%Y%m%d).tar.gz config.json logs/

# 恢复
tar -xzf backup-20240101.tar.gz
```