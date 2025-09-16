#!/usr/bin/env python3
"""
域名监控多群组迁移工具

帮助从单群组配置迁移到多群组配置
"""

import json
import sys
import os
from pathlib import Path

def load_config(config_file):
    """加载配置文件"""
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ 配置文件 {config_file} 不存在")
        return None
    except json.JSONDecodeError as e:
        print(f"❌ 配置文件格式错误: {e}")
        return None

def save_config(config, output_file):
    """保存配置文件"""
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)

def migrate_config(input_file, output_file=None):
    """迁移配置到多群组格式"""

    # 加载原配置
    config = load_config(input_file)
    if not config:
        return False

    # 检查是否已经是多群组格式
    telegram_config = config.get('telegram', {})
    if 'groups' in telegram_config:
        print("✅ 配置已经是多群组格式，无需迁移")
        return True

    # 获取单群组配置
    chat_id = telegram_config.get('chat_id')
    bot_token = telegram_config.get('bot_token')
    admin_users = telegram_config.get('admin_users', [])
    domains = config.get('domains', [])

    if not chat_id:
        print("❌ 未找到 chat_id，无法迁移")
        return False

    if not bot_token:
        print("❌ 未找到 bot_token，无法迁移")
        return False

    print(f"🔄 开始迁移配置...")
    print(f"  - 群组ID: {chat_id}")
    print(f"  - 域名数量: {len(domains)}")
    print(f"  - 管理员数量: {len(admin_users)}")

    # 创建多群组配置
    new_telegram_config = {
        "bot_token": bot_token,
        "groups": {
            str(chat_id): {
                "name": "默认监控群",
                "domains": domains,
                "admins": admin_users
            }
        }
    }

    # 如果有全局管理员，保留兼容性
    if admin_users:
        new_telegram_config["admin_users"] = admin_users

    # 更新配置
    config["telegram"] = new_telegram_config

    # 移除旧的domains配置（现在在groups中管理）
    if "domains" in config:
        del config["domains"]

    # 确定输出文件名
    if not output_file:
        base_name = Path(input_file).stem
        output_file = f"{base_name}-multigroup.json"

    # 保存新配置
    save_config(config, output_file)

    print(f"✅ 迁移完成！新配置已保存到: {output_file}")
    print(f"\n📋 新配置结构:")
    print(f"  - 群组: {chat_id}")
    print(f"  - 域名: {len(domains)} 个")
    print(f"  - 管理员: {len(admin_users)} 个")

    return True

def create_multigroup_config(output_file="config-multigroup-template.json"):
    """创建多群组配置模板"""

    template_config = {
        "telegram": {
            "bot_token": "YOUR_BOT_TOKEN_HERE",
            "groups": {
                "-1001234567890": {
                    "name": "项目A监控群",
                    "domains": [
                        "example-a1.com",
                        "example-a2.com"
                    ],
                    "admins": ["admin_user_a"]
                },
                "-1001234567891": {
                    "name": "项目B监控群",
                    "domains": [
                        "example-b1.com",
                        "example-b2.com"
                    ],
                    "admins": ["admin_user_b"]
                }
            }
        },
        "check": {
            "interval_minutes": 30,
            "timeout_seconds": 10,
            "retry_count": 2,
            "max_concurrent": 20,
            "auto_adjust_concurrent": True,
            "batch_notify": False,
            "show_eta": True
        },
        "notification": {
            "level": "smart",
            "failure_threshold": 2
        },
        "history": {
            "enabled": True,
            "retention_days": 30
        },
        "daily_report": {
            "enabled": True,
            "time": "09:00"
        },
        "http_api": {
            "enabled": False,
            "port": 8080,
            "auth": {
                "enabled": False,
                "api_key": ""
            }
        },
        "logging": {
            "level": "INFO",
            "file": "domain_monitor.log",
            "max_size_mb": 10,
            "backup_count": 5
        }
    }

    save_config(template_config, output_file)
    print(f"✅ 多群组配置模板已创建: {output_file}")
    print(f"\n📝 请修改以下内容:")
    print(f"  1. 替换 YOUR_BOT_TOKEN_HERE 为真实的Bot Token")
    print(f"  2. 替换群组ID (-1001234567890, -1001234567891)")
    print(f"  3. 配置每个群组的域名和管理员")
    print(f"  4. 调整监控参数")

def main():
    """主函数"""
    if len(sys.argv) < 2:
        print("🚀 域名监控多群组迁移工具")
        print("\n📖 使用方法:")
        print(f"  {sys.argv[0]} migrate <config.json> [output.json]    # 迁移现有配置")
        print(f"  {sys.argv[0]} template [output.json]                 # 创建配置模板")
        print("\n🎯 示例:")
        print(f"  {sys.argv[0]} migrate config.json                    # 迁移到 config-multigroup.json")
        print(f"  {sys.argv[0]} migrate config.json new-config.json    # 迁移到指定文件")
        print(f"  {sys.argv[0]} template                               # 创建模板文件")
        return

    command = sys.argv[1].lower()

    if command == "migrate":
        if len(sys.argv) < 3:
            print("❌ 请指定要迁移的配置文件")
            return

        input_file = sys.argv[2]
        output_file = sys.argv[3] if len(sys.argv) > 3 else None

        if not os.path.exists(input_file):
            print(f"❌ 配置文件 {input_file} 不存在")
            return

        success = migrate_config(input_file, output_file)
        if success:
            print(f"\n🎉 迁移成功！")
            print(f"\n📋 下一步:")
            print(f"  1. 检查生成的配置文件")
            print(f"  2. 使用新配置启动服务: python src/main.py --config {output_file or input_file.replace('.json', '-multigroup.json')}")
            print(f"  3. 在各群组中测试 /help 命令")
        else:
            print(f"\n❌ 迁移失败，请检查配置文件")

    elif command == "template":
        output_file = sys.argv[2] if len(sys.argv) > 2 else "config-multigroup-template.json"
        create_multigroup_config(output_file)

    else:
        print(f"❌ 未知命令: {command}")
        print(f"支持的命令: migrate, template")

if __name__ == "__main__":
    main()