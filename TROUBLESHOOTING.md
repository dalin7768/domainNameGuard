# 故障排查指南

## Linux 系统 stop/restart 问题修复

### 问题描述

在 Linux 系统上可能遇到以下问题：
1. 使用 `stop` 命令后服务自动重启
2. 使用 `restart` 命令无法正常重启服务

### 问题原因

这是由于 systemd 服务配置中的重启策略导致的：

```ini
# 旧配置（有问题）
Restart=on-failure
RestartPreventExitStatus=0
SuccessExitStatus=3

# 当程序正常退出（退出码0）时，systemd 认为这不是"成功"退出
# 因为 SuccessExitStatus 只包含 3，不包含 0
# 所以会触发重启
```

### 修复方案

已在新版 `deploy.sh` 中修复：

```ini
# 新配置（已修复）
Restart=on-failure
RestartPreventExitStatus=0
SuccessExitStatus=0 3

# 现在退出码 0 和 3 都被视为成功退出
# 0 = 正常停止，不重启
# 3 = 程序请求重启，允许重启
```

### 如何应用修复

#### 应用修复

使用新版 `deploy.sh` 脚本：

```bash
# 方法1：重新部署实例
./deploy.sh stop-all
./deploy.sh deploy client1  # 重新部署指定实例

# 方法2：更新现有实例
./deploy.sh update-all  # 更新所有实例
./deploy.sh update client1  # 更新指定实例
```

#### 手动修复现有服务

如果不想重新部署，可以手动编辑服务文件：

```bash
# 编辑服务文件（根据实例名称）
sudo nano /etc/systemd/system/domain-monitor-client1-client1.service
sudo nano /etc/systemd/system/domain-monitor-client1-client2.service
# ... 其他实例

# 在 [Service] 部分找到并修改：
SuccessExitStatus=0 3

# 重新加载配置
sudo systemctl daemon-reload

# 重启服务（根据实例名称）
sudo systemctl restart domain-monitor-client1-client1
```

## 常见问题排查

### 1. 服务无法停止

**症状**：使用 `systemctl stop` 或脚本 `stop` 命令后，服务立即重启

**排查步骤**：

```bash
# 检查服务配置
sudo systemctl cat domain-monitor-client1

# 查看 SuccessExitStatus 设置
# 应该是：SuccessExitStatus=0 3
```

**解决方案**：参照上面的修复方案

### 2. 服务无法重启

**症状**：使用 `restart` 命令后服务无法正常启动

**排查步骤**：

```bash
# 查看服务状态
sudo systemctl status domain-monitor-client1

# 查看详细日志
sudo journalctl -u domain-monitor-client1 -f

# 查看程序日志
tail -f /var/log/domain-monitor-client1-deploy.log
```

**可能原因**：
1. 配置文件错误
2. Python 环境问题
3. 端口被占用
4. 权限问题

### 3. 实例端口冲突

**症状**：多个实例无法同时启动

**排查步骤**：

```bash
# 检查端口占用
netstat -tlnp | grep :8000

# 查看实例状态
./deploy.sh status
```

**解决方案**：
1. 确保每个实例使用不同端口
2. 修改各实例的 `config-N.json` 文件
3. 重启相关实例

### 4. 权限问题

**症状**：服务启动失败，日志显示权限错误

**排查步骤**：

```bash
# 检查文件权限
ls -la config*.json
ls -la src/main.py

# 检查日志文件权限
ls -la /var/log/domain-monitor-client1*.log
```

**解决方案**：

```bash
# 修复文件权限
chmod 644 config*.json
chmod +x src/main.py

# 修复日志权限
sudo chown $USER:$USER /var/log/domain-monitor-client1*.log
```

## 测试修复是否成功

```bash
# 启动实例
sudo systemctl start domain-monitor-client1
# 或使用脚本：./deploy.sh start client1

# 等待几秒，确认服务运行
sudo systemctl is-active domain-monitor-client1

# 测试停止（应该不会重启）
sudo systemctl stop domain-monitor-client1
# 或使用脚本：./deploy.sh stop client1

# 等待几秒，确认服务已停止
sudo systemctl is-active domain-monitor-client1
# 应该输出：inactive

# 测试重启
sudo systemctl start domain-monitor-client1
sleep 5
sudo systemctl restart domain-monitor-client1
# 或使用脚本：./deploy.sh restart client1

# 确认重启成功
sudo systemctl is-active domain-monitor-client1
# 应该输出：active
```

## 预防措施

1. **定期备份配置**：
   ```bash
   tar -czf backup-$(date +%Y%m%d).tar.gz config*.json
   ```

2. **监控服务状态**：
   ```bash
   # 添加到 crontab，每5分钟检查一次
   */5 * * * * systemctl is-active --quiet domain-monitor-client1 || echo "Service down" | mail -s "Alert" your@email.com
   ```

3. **日志轮转检查**：
   ```bash
   # 检查日志轮转配置
   sudo logrotate -d /etc/logrotate.d/domain-monitor-client1*
   ```

## 紧急恢复

如果所有方法都失败，可以使用紧急恢复：

```bash
# 强制停止所有相关进程
sudo pkill -f "domain-monitor-client1"

# 删除服务文件
sudo rm /etc/systemd/system/domain-monitor-client1*.service

# 重新加载 systemd
sudo systemctl daemon-reload

# 重新部署（根据需要的实例）
./deploy.sh deploy client1
./deploy.sh deploy client2
```

## 联系支持

如果问题仍然存在，请收集以下信息：

```bash
# 系统信息
uname -a
systemctl --version

# 服务状态
sudo systemctl status domain-monitor-client1*

# 日志信息
sudo journalctl -u domain-monitor-client1* --no-pager

# 配置文件内容
cat config*.json

# 进程信息
ps aux | grep domain-monitor-client1
```