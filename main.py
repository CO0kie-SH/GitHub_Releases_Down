#!/usr/bin/env python3
"""
GitHub Releases 监控系统 - 主入口文件
执行命令：cmd /c "set PYTHONIOENCODING=utf-8 && D:\\0Code2\\py312\\python main.py"
"""

import asyncio
import sys
from pathlib import Path

# 添加脚本所在目录到 Python 路径
SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

from check_releases import logger, clean_old_logs


async def main():
    """主入口函数"""
    # 清理旧日志文件（保留30天）
    clean_old_logs(SCRIPT_DIR / "log", days=30)
    
    # 导入并执行主检查函数
    from check_releases import main as check_releases_main
    await check_releases_main()


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
        sys.exit(0)
    except Exception as e:
        logger.error(f"程序执行出错: {e}", exc_info=True)
        sys.exit(1)