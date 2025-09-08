#!/usr/bin/env python3
"""
便捷启动脚本
直接运行: python run.py
"""

import sys
import os

# 将src目录添加到Python路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

# 导入并运行主程序
from main import main

if __name__ == "__main__":
    main()