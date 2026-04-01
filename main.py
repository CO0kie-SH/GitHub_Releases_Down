#!/usr/bin/env python3
"""
GitHub Releases 监控系统 - 主入口文件
"""

import asyncio
import sys
import time
import logging
from pathlib import Path
from datetime import datetime

# 添加脚本所在目录到 Python 路径
SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR))

# 日志目录配置
LOG_DIR = SCRIPT_DIR / "log"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / datetime.now().strftime("%Y%m%d.log")

# 配置日志系统
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

from check_releases import clean_old_logs


async def main():
    """主入口函数"""
    # 清理旧日志文件（保留30天）
    clean_old_logs(SCRIPT_DIR / "log", days=30)
    
    # 导入并执行主检查函数
    from check_releases import main as check_releases_main
    await check_releases_main()


if __name__ == '__main__':
    print(f"[{int(time.time())}] 程序开始执行, SCRIPT_DIR={SCRIPT_DIR}, LOG_DIR={LOG_DIR}, LOG_FILE={LOG_FILE}")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("程序被用户中断")
        sys.exit(0)
    except Exception as e:
        logger.error(f"程序执行出错: {e}", exc_info=True)
        sys.exit(1)