# 多实例部署指南

本文档介绍如何使用 `deploy.sh` 脚本在同一台服务器上按名称管理多个域名监控程序实例。

## 功能特性

- ✅ 支持按名称创建和管理独立的监控实例
- ✅ 每个实例使用独立的配置文件和日志文件
- ✅ 基于 systemd 服务管理，开机自启
- ✅ 支持单独启动、停止、重启任意实例
- ✅ 支持批量操作（使用 -all 后缀）
- ✅ 统一的状态监控和管理命令
- ✅ 自动日志轮转，防止日志文件过大
- ✅ 实例名称验证，防止无效字符

## 使用场景

多实例部署适用于以下场景：

1. **多客户管理**: 为不同客户提供独立命名的监控服务（如 client1、client2）
2. **业务分类**: 按业务类型命名实例（如 web、api、cdn）
3. **环境隔离**: 按环境命名（如 prod、test、dev）
4. **地域分类**: 按地理区域命名（如 us、eu、asia）

## 快速开始

### 1. 部署实例

```bash
# 部署名为 client1 的实例
./deploy.sh deploy client1

# 部署名为 web-monitor 的实例
./deploy.sh deploy web-monitor

# 部署名为 production 的实例
./deploy.sh deploy production
```

### 2. 配置实例

部署完成后，需要编辑对应的配置文件：

```bash
# 编辑 client1 实例的配置
nano config-client1.json

# 编辑 web-monitor 实例的配置
nano config-web-monitor.json
```

**重要**: 确保每个配置文件中的以下参数不同：
- `telegram.chat_id` - 发送到不同的群组或频道
- `domains` - 监控不同的域名列表
- 如果使用HTTP API，需要配置不同的端口

### 3. 管理实例

```bash
# 查看所有实例状态
./deploy.sh status

# 查看指定实例状态
./deploy.sh status client1

# 启动指定实例
./deploy.sh start client1

# 停止指定实例
./deploy.sh stop client1

# 重启指定实例
./deploy.sh restart client1
```

## 详细命令说明

### 基本命令

```bash
# 部署新实例
./deploy.sh deploy <实例名称>

# 启动实例
./deploy.sh start <实例名称>

# 停止实例
./deploy.sh stop <实例名称>

# 重启实例
./deploy.sh restart <实例名称>

# 查看实例状态
./deploy.sh status [实例名称]

# 更新实例（重新加载代码）
./deploy.sh update [实例名称]

# 删除实例
./deploy.sh remove <实例名称>
```

### 批量操作

```bash
# 启动所有实例
./deploy.sh start-all

# 停止所有实例
./deploy.sh stop-all

# 更新所有实例
./deploy.sh update-all

# 删除所有实例（需要确认）
./deploy.sh remove-all
```

## 实例命名规则

实例名称必须符合以下规则：
- 只能包含字母、数字、连字符(-)和下划线(_)
- 不能为空
- 建议使用有意义的名称，如：
  - `client1`, `client2` - 按客户编号
  - `web-prod`, `api-prod` - 按业务和环境
  - `monitor-us`, `monitor-eu` - 按地理区域

## 文件结构

多实例部署后的文件结构如下：

```
项目目录/
├── deploy.sh                   # 部署脚本
├── config-client1.json         # client1实例配置文件
├── config-web-monitor.json     # web-monitor实例配置文件
├── config-production.json      # production实例配置文件
├── src/                        # 程序源代码
│   └── main.py
└── venv/                       # Python虚拟环境

系统文件:
/etc/systemd/system/
├── domain-monitor-client1.service      # client1服务文件
├── domain-monitor-web-monitor.service  # web-monitor服务文件
└── domain-monitor-production.service   # production服务文件

/var/log/
├── domain-monitor-client1.log          # client1日志
├── domain-monitor-web-monitor.log      # web-monitor日志
└── domain-monitor-production.log       # production日志

/etc/logrotate.d/
├── domain-monitor-client1              # client1日志轮转配置
├── domain-monitor-web-monitor          # web-monitor日志轮转配置
└── domain-monitor-production           # production日志轮转配置
```

## 配置示例

### client1 实例配置 (config-client1.json)

```json
{
    "telegram": {
        "bot_token": "你的Bot Token",
        "chat_id": "-100123456789"
    },
    "domains": [
        "client1-website.com",
        "client1-api.com"
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

### web-monitor 实例配置 (config-web-monitor.json)

```json
{
    "telegram": {
        "bot_token": "你的Bot Token",
        "chat_id": "-100987654321"
    },
    "domains": [
        "company-web.com",
        "company-blog.com",
        "company-shop.com"
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
./deploy.sh status

# 查看具体实例详情
sudo systemctl status domain-monitor-client1
sudo systemctl status domain-monitor-web-monitor
```

### 查看日志

```bash
# 查看 client1 实例日志
tail -f /var/log/domain-monitor-client1.log

# 查看 web-monitor 实例日志
tail -f /var/log/domain-monitor-web-monitor.log

# 查看系统日志
sudo journalctl -u domain-monitor-client1 -f
sudo journalctl -u domain-monitor-web-monitor -f
```

## 维护操作

### 更新代码

当你更新了程序代码后，需要重启相关实例：

```bash
# 更新所有实例
./deploy.sh update-all

# 或者单独更新某个实例
./deploy.sh update client1
```

### 修改配置

修改配置文件后，重启对应实例即可：

```bash
# 修改配置文件
nano config-client1.json

# 重启实例使配置生效
./deploy.sh restart client1
```

### 添加新实例

```bash
# 创建新实例
./deploy.sh deploy new-client

# 编辑配置文件
nano config-new-client.json

# 启动实例
./deploy.sh start new-client
```

### 删除实例

```bash
# 删除指定实例
./deploy.sh remove client1

# 这会停止服务、删除服务文件，但保留配置文件和日志
```

## 使用示例

### 场景1：为3个客户部署监控

```bash
# 部署3个客户的实例
./deploy.sh deploy client1
./deploy.sh deploy client2
./deploy.sh deploy client3

# 分别配置
nano config-client1.json  # 配置客户1的域名和通知群组
nano config-client2.json  # 配置客户2的域名和通知群组
nano config-client3.json  # 配置客户3的域名和通知群组

# 查看所有实例状态
./deploy.sh status
```

### 场景2：按业务类型部署

```bash
# 按业务类型部署
./deploy.sh deploy web-frontend
./deploy.sh deploy api-backend
./deploy.sh deploy cdn-assets

# 配置不同的检查间隔
# web-frontend: 每5分钟检查
# api-backend: 每1分钟检查
# cdn-assets: 每10分钟检查
```

### 场景3：按环境部署

```bash
# 按环境部署
./deploy.sh deploy production
./deploy.sh deploy staging
./deploy.sh deploy development

# 生产环境更频繁的检查和通知
# 测试环境较少的通知
# 开发环境仅记录日志
```

## 常见问题

### Q: 如何确定每个实例使用的配置文件？

A: 实例名为 NAME 的使用 `config-NAME.json` 文件，例如实例 client1 使用 `config-client1.json`。

### Q: 实例名称可以包含什么字符？

A: 只能包含字母、数字、连字符(-)和下划线(_)，不能包含空格或特殊字符。

### Q: 如何备份所有配置？

A: 备份所有 `config-*.json` 文件：
```bash
tar -czf config-backup-$(date +%Y%m%d).tar.gz config-*.json
```

### Q: 如何快速停止所有实例？

A: 使用批量停止命令：
```bash
./deploy.sh stop-all
```

### Q: 实例之间会相互影响吗？

A: 不会。每个实例是完全独立的进程，使用独立的配置、日志和服务。

### Q: 如何监控所有实例的运行状态？

A: 使用 `./deploy.sh status` 可以快速查看所有实例状态。

## 性能建议

1. **合理分配域名**: 建议每个实例监控50-100个域名
2. **错开检查时间**: 不同实例可以设置不同的检查间隔
3. **使用有意义的名称**: 便于管理和识别
4. **定期清理**: 删除不再需要的实例和配置

## 迁移指南

### 从数字编号迁移到名称

如果你之前使用数字编号的实例部署，可以这样迁移：

```bash
# 1. 停止所有旧实例
./deploy.sh stop-all

# 2. 备份配置文件
cp config-1.json config-client1.json
cp config-2.json config-client2.json

# 3. 删除旧实例
./deploy.sh remove-all

# 4. 部署新的命名实例
./deploy.sh deploy client1
./deploy.sh deploy client2

# 5. 验证服务正常运行
./deploy.sh status
```

有问题请检查日志文件或使用 `systemctl status` 命令查看服务状态。