# 配置指南

## 📋 配置文件说明

配置文件 `config.json` 包含所有服务设置。复制 `config_example.json` 并重命名为 `config.json` 开始配置。

## 🔧 配置项详解

### 1. Telegram 配置 (`telegram`)

| 配置项 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| `bot_token` | string | ✅ | Telegram Bot Token |
| `chat_id` | string | ✅ | 群组或频道 ID（负数） |
| `admin_users` | array | ❌ | 管理员用户名列表 |

**获取方法：**

#### Bot Token
1. 在 Telegram 中搜索 @BotFather
2. 发送 `/newbot` 创建新机器人
3. 按提示设置机器人名称和用户名
4. 获得 Token（格式：`1234567890:ABCdefGHI...`）

#### Chat ID
1. 将机器人加入目标群组
2. 在群组发送任意消息
3. 访问：`https://api.telegram.org/bot<TOKEN>/getUpdates`
4. 找到 `"chat":{"id":-1234567890}`，这个负数即为群组ID

#### Admin Users
- 格式：`["@username1", "@username2"]`
- 注意：使用 @ 开头的用户名，不是数字ID

### 2. 检查配置 (`check`)

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `interval_minutes` | int | 30 | 检查间隔（1-1440分钟） |
| `max_concurrent` | int | 10 | 最大并发数（1-100） |
| `auto_adjust_concurrent` | bool | true | 自动调整并发数 |
| `timeout_seconds` | int | 10 | 请求超时（1-300秒） |
| `retry_count` | int | 2 | 重试次数（0-10） |
| `retry_delay_seconds` | int | 5 | 重试延迟（1-60秒） |
| `batch_notify` | bool | false | 分批通知结果 |
| `show_eta` | bool | true | 显示预计完成时间 |

**性能调优建议：**
- 域名数 < 50：`max_concurrent=10`
- 域名数 50-200：`max_concurrent=20`
- 域名数 > 200：`max_concurrent=50`，启用 `auto_adjust_concurrent`

### 3. 域名列表 (`domains`)

支持两种格式：

#### 简单格式
```json
"domains": [
  "example.com",
  "test.com",
  "api.example.com"
]
```

#### 详细格式（未来支持）
```json
"domains": [
  {
    "url": "example.com",
    "name": "主站",
    "expected_codes": [200, 301]
  }
]
```

**注意事项：**
- 无需添加 `http://` 或 `https://` 前缀
- 程序会自动使用 HTTPS 协议
- 支持子域名和路径

### 4. 通知配置 (`notification`)

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `notify_on_recovery` | bool | true | 域名恢复时通知 |
| `notify_on_all_success` | bool | false | 全部正常时通知 |
| `failure_threshold` | int | 1 | 连续失败N次才告警 |
| `cooldown_minutes` | int | 60 | 告警冷却时间 |

**告警策略：**
- `failure_threshold=1`：立即告警（推荐）
- `failure_threshold=3`：连续3次失败才告警（减少误报）
- `cooldown_minutes=60`：同一域名1小时内不重复告警

### 5. 日志配置 (`logging`)

| 配置项 | 类型 | 默认值 | 说明 |
|--------|------|--------|------|
| `level` | string | INFO | 日志级别 |
| `file` | string | domain_monitor.log | 日志文件名 |
| `max_size_mb` | int | 10 | 单文件最大大小 |
| `backup_count` | int | 5 | 保留历史文件数 |

**日志级别：**
- `DEBUG`：详细调试信息
- `INFO`：正常运行信息（推荐）
- `WARNING`：警告信息
- `ERROR`：仅错误信息

## 📝 完整配置示例

### 最小配置
```json
{
  "telegram": {
    "bot_token": "YOUR_BOT_TOKEN",
    "chat_id": "-1234567890"
  },
  "domains": [
    "example.com"
  ]
}
```

### 标准配置
```json
{
  "telegram": {
    "bot_token": "YOUR_BOT_TOKEN",
    "chat_id": "-1234567890",
    "admin_users": ["@admin1", "@admin2"]
  },
  "check": {
    "interval_minutes": 30,
    "max_concurrent": 20,
    "timeout_seconds": 10,
    "retry_count": 2
  },
  "domains": [
    "example.com",
    "api.example.com",
    "cdn.example.com"
  ],
  "notification": {
    "notify_on_recovery": true,
    "failure_threshold": 2,
    "cooldown_minutes": 30
  }
}
```

### 高性能配置（大量域名）
```json
{
  "telegram": {
    "bot_token": "YOUR_BOT_TOKEN",
    "chat_id": "-1234567890",
    "admin_users": ["@admin"]
  },
  "check": {
    "interval_minutes": 10,
    "max_concurrent": 50,
    "auto_adjust_concurrent": true,
    "timeout_seconds": 5,
    "retry_count": 1,
    "batch_notify": false,
    "show_eta": true
  },
  "domains": [
    "... 数百个域名 ..."
  ],
  "notification": {
    "notify_on_recovery": false,
    "notify_on_all_success": false,
    "failure_threshold": 3,
    "cooldown_minutes": 60
  },
  "logging": {
    "level": "WARNING",
    "max_size_mb": 50,
    "backup_count": 10
  }
}
```

## 🔄 动态配置管理

### 通过 Telegram 命令修改

大部分配置可通过 Telegram 命令实时修改，无需重启服务：

```
/interval 10        # 设置检查间隔为10分钟
/timeout 15         # 设置超时为15秒
/retry 3           # 设置重试3次
/threshold 2       # 连续失败2次才告警
/cooldown 30       # 设置冷却时间30分钟
/recovery          # 切换恢复通知开关
/reload           # 重新加载配置文件
```

### 配置热重载

修改 `config.json` 后，使用 `/reload` 命令即可生效，支持：
- ✅ 域名列表更新
- ✅ 检查参数调整
- ✅ 通知设置变更
- ❌ Bot Token（需重启）
- ❌ Chat ID（需重启）

## ⚠️ 注意事项

1. **配置文件权限**：生产环境建议设置为 `600`，仅所有者可读写
2. **敏感信息保护**：不要将包含 Token 的配置文件提交到代码仓库
3. **定期备份**：建议定期备份配置文件
4. **测试配置**：修改后先在测试环境验证
5. **监控资源**：大量域名时注意服务器资源使用

## 🆘 常见问题

### Q: 如何判断配置是否正确？
A: 启动程序时会自动验证配置并测试 Telegram 连接。

### Q: 修改配置后需要重启吗？
A: 大部分配置支持热重载，使用 `/reload` 命令即可。

### Q: 支持多少个域名？
A: 理论上无限制，实际取决于服务器性能。建议：
- 1核1G：< 100个域名
- 2核2G：100-500个域名
- 4核4G：> 500个域名

### Q: 如何优化检查速度？
A: 
1. 增加 `max_concurrent` 值
2. 减少 `timeout_seconds`
3. 减少 `retry_count`
4. 启用 `auto_adjust_concurrent`

### Q: 告警太频繁怎么办？
A: 
1. 增加 `failure_threshold` 值
2. 增加 `cooldown_minutes` 时间
3. 关闭 `notify_on_recovery`