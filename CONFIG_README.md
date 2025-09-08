# 配置文件说明

## config.json 配置项详解

### 1. Telegram 配置 (telegram)

| 配置项 | 类型 | 说明 | 示例 |
|--------|------|------|------|
| `bot_token` | string | Telegram Bot Token | "1234567890:ABCdefGHI..." |
| `chat_id` | string | 群组或频道 ID | "-1001234567890" |
| `admin_users` | array | 管理员用户 ID 列表 | [123456, 789012] |

**获取方法：**
- `bot_token`: 在 Telegram 中找到 @BotFather，发送 /newbot 创建机器人
- `chat_id`: 将机器人加入群组后，访问 `https://api.telegram.org/bot<TOKEN>/getUpdates` 查看
- `admin_users`: 用户发送消息后，从 getUpdates 中获取 user.id

### 2. 检查配置 (check)

| 配置项 | 类型 | 范围 | 说明 |
|--------|------|------|------|
| `interval_minutes` | int | 1-1440 | 定时检查的间隔时间 |
| `timeout_seconds` | int | 1-300 | HTTP 请求超时时间 |
| `retry_count` | int | 0-10 | 失败后的重试次数 |
| `retry_delay_seconds` | int | 1-60 | 重试之间的等待时间 |

### 3. 域名列表 (domains)

- 类型：字符串数组
- 格式：必须以 `http://` 或 `https://` 开头的完整 URL
- 示例：`["https://example.com", "https://api.example.com/health"]`

### 4. 通知配置 (notification)

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `notify_on_recovery` | bool | 域名恢复时是否通知 |
| `failure_threshold` | int | 连续失败几次才告警 |
| `cooldown_minutes` | int | 告警冷却时间，避免频繁通知 |

### 5. 日志配置 (logging)

| 配置项 | 类型 | 说明 |
|--------|------|------|
| `level` | string | 日志级别：DEBUG/INFO/WARNING/ERROR |
| `file` | string | 日志文件名 |
| `max_size_mb` | int | 单个日志文件最大大小 |
| `backup_count` | int | 保留的历史日志文件数 |

## Telegram 命令说明

所有命令都需要在群组中 @机器人 发送，例如：`@your_bot /add https://example.com`

### 基础命令
- `/help` - 显示帮助信息
- `/start` - 启动机器人
- `/status` - 查看监控状态
- `/list` - 列出所有监控域名

### 域名管理
- `/add <url>` - 添加域名
- `/remove <url>` - 删除域名
- `/clear` - 清空所有域名

### 监控控制
- `/check` - 立即执行一次检查
- `/stop` - 停止监控服务
- `/restart` - 重启监控服务

### 配置管理
- `/config` - 显示当前配置
- `/interval <分钟>` - 设置检查间隔
- `/timeout <秒>` - 设置超时时间
- `/retry <次数>` - 设置重试次数
- `/threshold <次数>` - 设置失败阈值
- `/cooldown <分钟>` - 设置冷却时间
- `/recovery` - 切换恢复通知开关

### 管理员管理
- `/admin add <user_id>` - 添加管理员
- `/admin remove <user_id>` - 移除管理员
- `/admin list` - 列出所有管理员

## 注意事项

1. **JSON 格式**：标准 JSON 不支持注释，config.json 中不能包含 // 注释
2. **配置更新**：通过 Telegram 命令修改的配置会立即生效并保存到文件
3. **权限控制**：如果设置了 admin_users，只有管理员可以修改配置
4. **冷却机制**：避免同一域名短时间内重复告警
5. **失败阈值**：避免网络抖动导致的误报