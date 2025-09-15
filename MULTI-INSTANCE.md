# 多实例部署指南

本文档介绍如何使用 `deploy-multi.sh` 脚本在同一台服务器上同时运行多个域名监控程序实例。

## 功能特性

- ✅ 支持同时运行多个独立的监控实例
- ✅ 每个实例使用独立的配置文件和日志文件
- ✅ 基于 systemd 服务管理，开机自启
- ✅ 支持单独启动、停止、重启任意实例
- ✅ 统一的状态监控和管理命令
- ✅ 自动日志轮转，防止日志文件过大

## 使用场景

多实例部署适用于以下场景：

1. **多客户监控**: 为不同客户提供独立的域名监控服务
2. **业务隔离**: 不同业务线的域名分别监控，避免互相影响
3. **负载分散**: 大量域名分散到多个实例，降低单实例压力
4. **配置差异**: 不同实例使用不同的检查间隔、通知设置等

## 快速开始

### 1. 部署多个实例

```bash
# 部署3个实例
./deploy-multi.sh deploy 3
```

### 2. 配置各实例

部署完成后，需要分别编辑各实例的配置文件：

```bash
# 编辑实例1的配置
nano config-1.json

# 编辑实例2的配置
nano config-2.json

# 编辑实例3的配置
nano config-3.json
```

**重要**: 确保每个配置文件中的以下参数不同：
- `telegram.chat_id` - 发送到不同的群组或频道
- `domains` - 监控不同的域名列表
- 如果使用HTTP API，需要配置不同的端口

### 3. 启动实例

```bash
# 启动所有实例
./deploy-multi.sh start-all

# 或者单独启动指定实例
./deploy-multi.sh start 1
./deploy-multi.sh start 2
./deploy-multi.sh start 3
```

## 详细命令说明

### 部署命令

```bash
# 部署N个实例
./deploy-multi.sh deploy N

# 示例：部署5个实例
./deploy-multi.sh deploy 5
```

### 管理命令

```bash
# 查看所有实例状态
./deploy-multi.sh status

# 查看指定实例状态
./deploy-multi.sh status 2

# 启动指定实例
./deploy-multi.sh start 2

# 停止指定实例
./deploy-multi.sh stop 2

# 重启指定实例
./deploy-multi.sh restart 2

# 启动所有实例
./deploy-multi.sh start-all

# 停止所有实例
./deploy-multi.sh stop-all

# 更新所有实例（重新加载代码）
./deploy-multi.sh update

# 更新指定实例
./deploy-multi.sh update 2

# 删除指定实例
./deploy-multi.sh remove 2
```

## 文件结构

多实例部署后的文件结构如下：

```
项目目录/
├── deploy-multi.sh          # 多实例部署脚本
├── config-1.json           # 实例1配置文件
├── config-2.json           # 实例2配置文件
├── config-3.json           # 实例3配置文件
├── src/                    # 程序源代码
│   └── main.py
└── venv/                   # Python虚拟环境

系统文件:
/etc/systemd/system/
├── domain-monitor-1.service # 实例1服务文件
├── domain-monitor-2.service # 实例2服务文件
└── domain-monitor-3.service # 实例3服务文件

/var/log/
├── domain-monitor-1.log     # 实例1日志
├── domain-monitor-2.log     # 实例2日志
└── domain-monitor-3.log     # 实例3日志

/etc/logrotate.d/
├── domain-monitor-1         # 实例1日志轮转配置
├── domain-monitor-2         # 实例2日志轮转配置
└── domain-monitor-3         # 实例3日志轮转配置
```

## 配置示例

### 实例1配置 (config-1.json)

```json
{
    "telegram": {
        "bot_token": "你的Bot Token",
        "chat_id": "-100123456789"
    },
    "domains": [
        "example1.com",
        "test1.com"
    ],
    "check": {
        "interval_minutes": 30,
        "timeout_seconds": 10,
        "max_concurrent": 50
    },
    "notification": {
        "level": "smart",
        "failure_threshold": 2
    }
}
```

### 实例2配置 (config-2.json)

```json
{
    "telegram": {
        "bot_token": "你的Bot Token",
        "chat_id": "-100987654321"
    },
    "domains": [
        "example2.com",
        "test2.com"
    ],
    "check": {
        "interval_minutes": 15,
        "timeout_seconds": 10,
        "max_concurrent": 30
    },
    "notification": {
        "level": "all"
    }
}
```

## 监控和日志

### 查看实例状态

```bash
# 查看所有实例概览
./deploy-multi.sh status

# 查看具体实例详情
sudo systemctl status domain-monitor-1
sudo systemctl status domain-monitor-2
sudo systemctl status domain-monitor-3
```

### 查看日志

```bash
# 查看实例1日志
tail -f /var/log/domain-monitor-1.log

# 查看实例2日志
tail -f /var/log/domain-monitor-2.log

# 查看实例3日志
tail -f /var/log/domain-monitor-3.log

# 查看最近的错误日志
sudo journalctl -u domain-monitor-1 -f
sudo journalctl -u domain-monitor-2 -f
sudo journalctl -u domain-monitor-3 -f
```

## 维护操作

### 更新代码

当你更新了程序代码后，需要重启所有实例：

```bash
# 更新所有实例
./deploy-multi.sh update

# 或者单独更新某个实例
./deploy-multi.sh update 2
```

### 修改配置

修改配置文件后，重启对应实例即可：

```bash
# 修改配置文件
nano config-1.json

# 重启实例使配置生效
./deploy-multi.sh restart 1
```

### 添加新实例

如果需要添加新实例：

```bash
# 假设当前有3个实例，要添加第4个
# 创建第4个实例的配置文件
cp config_example.json config-4.json
nano config-4.json

# 部署第4个实例（注意：这会检查环境但只创建第4个）
# 需要手动创建
sudo ./deploy-multi.sh deploy 4  # 这会重新创建所有实例
```

建议方法是重新部署所有实例：
```bash
# 停止所有当前实例
./deploy-multi.sh stop-all

# 重新部署4个实例
./deploy-multi.sh deploy 4
```

### 删除实例

```bash
# 删除第3个实例
./deploy-multi.sh remove 3

# 这会停止服务、删除服务文件，但保留配置文件和日志
```

## 常见问题

### Q: 如何确定每个实例使用的配置文件？

A: 实例N使用 `config-N.json` 文件，例如实例1使用 `config-1.json`。

### Q: 实例之间会相互影响吗？

A: 不会。每个实例是完全独立的进程，使用独立的配置、日志和服务。

### Q: 如何监控所有实例的运行状态？

A: 使用 `./deploy-multi.sh status` 可以快速查看所有实例状态。

### Q: 日志文件会无限增长吗？

A: 不会。脚本自动配置了日志轮转，日志文件最大50MB，保留3个历史版本。

### Q: 如何备份配置？

A: 备份所有 `config-*.json` 文件即可：
```bash
tar -czf config-backup-$(date +%Y%m%d).tar.gz config-*.json
```

### Q: 可以在Windows上使用吗？

A: 此脚本是为Linux设计的。Windows用户请参考原始的 `deploy.sh` 脚本，手动创建多个配置文件并分别运行。

## 性能建议

1. **合理分配域名**: 建议每个实例监控50-100个域名
2. **错开检查时间**: 不同实例可以设置不同的检查间隔
3. **监控系统资源**: 使用 `htop` 等工具监控CPU和内存使用
4. **磁盘空间**: 定期清理旧日志文件

## 技术原理

- 每个实例是独立的 systemd 服务
- 服务名格式：`domain-monitor-N`
- 配置文件通过 `--config` 参数传递给主程序
- 日志输出到独立文件：`/var/log/domain-monitor-N.log`
- 支持通过环境变量 `CONFIG_FILE` 指定配置文件

有问题请检查日志文件或使用 `systemctl status` 命令查看服务状态。