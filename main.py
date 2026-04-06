#!/usr/bin/env python3
"""
GitHub Releases monitor - program entry.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

from version import __version__

class ReleaseMonitorApp:
    def __init__(self) -> None:
        self.script_dir = Path(__file__).parent.resolve()
        sys.path.insert(0, str(self.script_dir))

        self.log_dir = self.script_dir / "log"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / datetime.now().strftime("%Y%m%d.log")
        self.logger = self._configure_logging()

    def _configure_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            handlers=[logging.FileHandler(self.log_file, encoding="utf-8"), logging.StreamHandler()],
        )
        return logging.getLogger(__name__)

    async def run(self) -> None:
        from check_releases import GitHubReleaseChecker

        checker = GitHubReleaseChecker(script_dir=self.script_dir)
        checker.clean_old_logs(self.log_dir, days=30)
        await checker.run()


def main() -> None:
    app = ReleaseMonitorApp()
    print(
        f"[{int(time.time())}] Program started v{__version__} "
        f"SCRIPT_DIR={app.script_dir}, LOG_DIR={app.log_dir}, LOG_FILE={app.log_file}"
    )
    try:
        asyncio.run(app.run())
    except KeyboardInterrupt:
        app.logger.info("Program interrupted by user")
        sys.exit(0)
    except Exception as e:
        app.logger.error(f"Program execution failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
