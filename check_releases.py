#!/usr/bin/env python3
"""
GitHub Releases checker (async).
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

import aiohttp

from download_workflow import DownloadWorkflow


@dataclass
class CheckerPaths:
    script_dir: Path

    @property
    def csv_file(self) -> Path:
        return self.script_dir / "github.csv"

    @property
    def output_file(self) -> Path:
        return self.script_dir / "releases.json"

    @property
    def download_dir(self) -> Path:
        return self.script_dir / "releases"

    @property
    def tmp_dir(self) -> Path:
        return self.script_dir / "tmp"

    @property
    def log_dir(self) -> Path:
        return self.script_dir / "log"

    @property
    def db_dir(self) -> Path:
        return self.script_dir / "db"


class GitHubReleaseChecker:
    SHIELDS_API = "https://img.shields.io/github/v/release"
    XGET_API = "https://xget.xi-xu.me/gh"
    GHPROXY_URL = "https://ghproxy.net"

    def __init__(self, script_dir: Path | None = None, request_delay: float = 3.0):
        self.script_dir = script_dir or Path(__file__).parent.resolve()
        if Path(__file__).is_symlink():
            self.script_dir = Path(__file__).resolve().parent

        self.paths = CheckerPaths(self.script_dir)
        self.logger = logging.getLogger(__name__)
        self.request_delay = request_delay
        self.github_token = os.environ.get("GITHUB_TOKEN")
        self.workflow = DownloadWorkflow(logger=self.logger)

    def clean_old_logs(self, log_dir: Path | None = None, days: int = 30) -> None:
        target_log_dir = log_dir or self.paths.log_dir
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            for log_file in target_log_dir.glob("*.log"):
                if log_file.is_file():
                    file_mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                    if file_mtime < cutoff_date:
                        log_file.unlink()
                        self.logger.info(f"Deleted old log file: {log_file.name}")
        except Exception as e:
            self.logger.error(f"Failed to clean old logs: {e}")

    async def get_release_assets_via_xget(
        self,
        session: aiohttp.ClientSession,
        owner: str,
        repo: str,
        version: str,
        max_retries: int = 3,
        retry_delay: float = 5.0,
    ) -> list[dict] | None:
        versions_to_try = [version, version.lstrip("v")]
        if versions_to_try[0] == versions_to_try[1]:
            versions_to_try = [version]

        for xget_version in versions_to_try:
            url = f"{self.XGET_API}/{owner}/{repo}/releases/expanded_assets/{xget_version}"

            for attempt in range(max_retries):
                try:
                    async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                        if response.status == 429:
                            retry_after = response.headers.get("Retry-After")
                            wait_time = float(retry_after) if retry_after else retry_delay * (2 ** attempt)
                            self.logger.warning(
                                f"{owner}/{repo}/{xget_version}: HTTP 429, waiting {wait_time}s "
                                f"(attempt {attempt + 1}/{max_retries})"
                            )
                            if attempt < max_retries - 1:
                                await asyncio.sleep(wait_time)
                                continue
                            break

                        if response.status == 404:
                            break

                        if response.status != 200:
                            self.logger.error(f"{owner}/{repo}/{xget_version}: HTTP {response.status}")
                            break

                        data = await response.text()
                        assets: list[dict] = []
                        li_pattern = r'<li[^>]*class="Box-row[^"]*"[^>]*>(.*?)</li>'
                        li_matches = re.findall(li_pattern, data, re.DOTALL)

                        for li_content in li_matches:
                            asset: dict = {}

                            a_match = re.search(
                                r'<a href="([^"]+)"[^>]*>\s*<span[^>]*class="Truncate-text text-bold[^"]*"[^>]*>([^<]+)</span>',
                                li_content,
                            )
                            if a_match:
                                relative_url = a_match.group(1)
                                asset["filename"] = a_match.group(2).strip()
                                asset["download_url"] = f"https://github.com{relative_url}"

                            sha_match = re.search(r"sha256:([a-f0-9]{64})", li_content)
                            if sha_match:
                                asset["sha256"] = sha_match.group(1)

                            size_match = re.search(r"(\d+(?:\.\d+)?\s*[KMGT]?B)</span>", li_content)
                            if size_match:
                                asset["size"] = size_match.group(1)

                            time_match = re.search(r'datetime="([^"]+)"', li_content)
                            if time_match:
                                asset["published_at"] = time_match.group(1)

                            if asset.get("download_url") and "archive/refs/tags" not in asset.get("download_url", ""):
                                assets.append(asset)

                        if assets:
                            return assets
                        break

                except asyncio.TimeoutError:
                    self.logger.error(f"{owner}/{repo}/{xget_version}: Timeout (attempt {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    break
                except aiohttp.ClientError as e:
                    self.logger.error(f"{owner}/{repo}/{xget_version}: {e} (attempt {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    break
                except Exception as e:
                    self.logger.error(f"{owner}/{repo}/{xget_version}: {e}")
                    break

        self.logger.warning(f"{owner}/{repo}/{version}: No assets found (xget)")
        return None

    async def get_latest_release_via_shields(
        self,
        session: aiohttp.ClientSession,
        owner: str,
        repo: str,
        max_retries: int = 3,
    ) -> dict | None:
        url = f"{self.SHIELDS_API}/{owner}/{repo}"

        for attempt in range(max_retries):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 429:
                        retry_after = response.headers.get("Retry-After")
                        wait_time = float(retry_after) if retry_after else 5.0 * (2 ** attempt)
                        self.logger.warning(
                            f"{owner}/{repo}: HTTP 429, waiting {wait_time}s "
                            f"(attempt {attempt + 1}/{max_retries})"
                        )
                        if attempt < max_retries - 1:
                            await asyncio.sleep(wait_time)
                            continue
                        return None

                    if response.status != 200:
                        self.logger.error(f"{owner}/{repo}: HTTP {response.status} (attempt {attempt + 1}/{max_retries})")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2)
                            continue
                        return None

                    data = await response.text()
                    match = re.search(r"<title>([^<]+)</title>", data)
                    if match:
                        title = match.group(1)
                        if ":" in title:
                            version = title.split(":", 1)[1].strip()
                            if version and version.lower() not in ("none", "no releases"):
                                return {"tag_name": version, "source": "shields.io"}
                            self.logger.warning(f"{owner}/{repo}: No releases found (shields.io)")
                            return None
                        self.logger.warning(f"{owner}/{repo}: Unexpected title format: {title}")
                        return None

                    self.logger.warning(f"{owner}/{repo}: No title found in SVG")
                    return None

            except asyncio.TimeoutError:
                self.logger.error(f"{owner}/{repo}: Timeout (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                    continue
                return None
            except aiohttp.ClientError as e:
                self.logger.error(f"{owner}/{repo}: {e} (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                    continue
                return None
            except Exception as e:
                self.logger.error(f"{owner}/{repo}: {e}")
                return None

        return None

    @staticmethod
    def calculate_sha256(file_path: str) -> str:
        sha256_hash = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256_hash.update(chunk)
        return sha256_hash.hexdigest()

    async def download_file(
        self,
        session: aiohttp.ClientSession,
        url: str,
        dest_path: str,
        expected_sha256: str | None = None,
        max_retries: int = 3,
    ) -> dict:
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)

        for attempt in range(max_retries):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as response:
                    if response.status == 429:
                        retry_after = response.headers.get("Retry-After")
                        wait_time = float(retry_after) if retry_after else 5.0 * (2 ** attempt)
                        self.logger.warning(f"Download: HTTP 429, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(wait_time)
                            continue
                        return {"success": False, "error": "HTTP 429"}

                    if response.status != 200:
                        self.logger.error(f"Download failed: HTTP {response.status} (attempt {attempt + 1}/{max_retries})")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(2)
                            continue
                        return {"success": False, "error": f"HTTP {response.status}"}

                    with open(dest_path, "wb") as f:
                        while True:
                            chunk = await response.content.read(8192)
                            if not chunk:
                                break
                            f.write(chunk)

                if expected_sha256:
                    actual_sha256 = self.calculate_sha256(dest_path)
                    if actual_sha256 != expected_sha256:
                        self.logger.error(
                            f"SHA256 mismatch: expected {expected_sha256}, got {actual_sha256}"
                        )
                        os.remove(dest_path)
                        return {
                            "success": False,
                            "error": "SHA256 mismatch",
                            "expected_sha256": expected_sha256,
                            "actual_sha256": actual_sha256,
                        }

                file_size = os.path.getsize(dest_path)
                return {
                    "success": True,
                    "file_path": dest_path,
                    "file_size": file_size,
                    "sha256": expected_sha256 or self.calculate_sha256(dest_path),
                }

            except asyncio.TimeoutError:
                self.logger.error(f"Download timeout (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                    continue
                return {"success": False, "error": "Timeout"}
            except aiohttp.ClientError as e:
                self.logger.error(f"Download failed: {e} (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                    continue
                return {"success": False, "error": str(e)}
            except Exception as e:
                self.logger.error(f"Download failed: {e} (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(2)
                    continue
                return {"success": False, "error": str(e)}

        return {"success": False, "error": "Max retries exceeded"}

    def read_csv(self) -> list[dict]:
        repos: list[dict] = []
        if not self.paths.csv_file.exists():
            self.logger.error(f"CSV file not found: {self.paths.csv_file}")
            return repos

        with open(self.paths.csv_file, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                repos.append(
                    {
                        "tag": (row.get("tag") or "").strip(),
                        "owner": (row.get("owner") or "").strip(),
                        "repo": (row.get("repo") or "").strip(),
                        "current_version": (row.get("current_version") or "").strip(),
                        "latest_version": (row.get("latest_version") or "").strip(),
                        "last_checked": (row.get("last_checked") or "").strip(),
                    }
                )
        return repos

    def write_csv(self, repos: list[dict]) -> None:
        with open(self.paths.csv_file, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=["tag", "owner", "repo", "current_version", "latest_version", "last_checked"],
            )
            writer.writeheader()
            for repo in repos:
                writer.writerow(
                    {
                        "tag": repo.get("tag", ""),
                        "owner": repo["owner"],
                        "repo": repo["repo"],
                        "current_version": repo["current_version"],
                        "latest_version": repo.get("latest_version", ""),
                        "last_checked": repo.get("last_checked", ""),
                    }
                )

    async def check_repo(
        self,
        session: aiohttp.ClientSession,
        repo: dict,
        index: int,
        now_timestamp: int,
    ) -> dict:
        tag = repo["tag"]
        owner = repo["owner"]
        repo_name = repo["repo"]
        current_version = repo["current_version"]

        if index > 0:
            self.logger.info(f"Waiting {self.request_delay}s before next request...")
            await asyncio.sleep(self.request_delay)

        print(f"[FLOW] Checking {owner}/{repo_name}...")

        release = await self.get_latest_release_via_shields(session, owner, repo_name)

        if release is None:
            return {
                "tag": tag,
                "owner": owner,
                "repo": repo_name,
                "latest_version": None,
                "current_version": current_version,
                "has_update": False,
                "html_url": f"https://github.com/{owner}/{repo_name}/releases",
                "last_checked": now_timestamp,
                "assets": None,
                "error": "Failed to fetch release info",
            }

        latest_version = release["tag_name"]
        has_update = latest_version != current_version and latest_version != ""

        print(f"[FLOW] Fetching assets for {owner}/{repo_name}/{latest_version}...")
        assets = await self.get_release_assets_via_xget(session, owner, repo_name, latest_version)

        downloaded_assets = await self.workflow.download_assets_if_needed(
            session=session,
            tag=tag,
            owner=owner,
            repo_name=repo_name,
            latest_version=latest_version,
            assets=assets,
            has_update=has_update,
            download_assets_func=self.workflow.download_assets,
            download_assets_kwargs={
                "download_dir": self.paths.download_dir,
                "tmp_dir": self.paths.tmp_dir,
                "ghproxy_url": self.GHPROXY_URL,
                "calculate_sha256_func": self.calculate_sha256,
                "download_file_func": self.download_file,
            },
        )

        result = {
            "tag": tag,
            "owner": owner,
            "repo": repo_name,
            "latest_version": latest_version,
            "current_version": current_version,
            "has_update": has_update,
            "html_url": f"https://github.com/{owner}/{repo_name}/releases/tag/{latest_version}",
            "last_checked": now_timestamp,
            "assets": assets,
            "downloaded_assets": downloaded_assets,
        }

        repo["latest_version"] = latest_version
        repo["last_checked"] = str(now_timestamp)

        return result

    async def run(self) -> None:
        now_timestamp = int(time.time())
        print(f"[FLOW] Starting GitHub releases check at timestamp {now_timestamp}")

        repos = self.read_csv()
        if not repos:
            print("[FLOW] No repositories to check")
            return

        results: list[dict] = []
        updates_found: list[dict] = []

        headers = {"User-Agent": "OpenClaw-GitHub-Releases-Checker/1.0"}
        async with aiohttp.ClientSession(headers=headers) as session:
            for i, repo in enumerate(repos):
                result = await self.check_repo(session, repo, i, now_timestamp)
                results.append(result)

                if result.get("has_update"):
                    updates_found.append(
                        {
                            "tag": result["tag"],
                            "owner": result["owner"],
                            "repo": result["repo"],
                            "old_version": result["current_version"],
                            "new_version": result["latest_version"],
                            "assets": result.get("assets"),
                            "downloaded_assets": result.get("downloaded_assets"),
                        }
                    )

        await self.workflow.persist_and_notify(
            output_file=self.paths.output_file,
            results=results,
            repos=repos,
            updates_found=updates_found,
            write_csv_func=self.write_csv,
        )


# Backward-compatible module-level APIs
_default_checker: GitHubReleaseChecker | None = None


def _get_default_checker() -> GitHubReleaseChecker:
    global _default_checker
    if _default_checker is None:
        _default_checker = GitHubReleaseChecker(logger=logging.getLogger(__name__))
    return _default_checker


def clean_old_logs(log_dir: Path, days: int = 30) -> None:
    _get_default_checker().clean_old_logs(log_dir=log_dir, days=days)


async def main() -> None:
    await _get_default_checker().run()


def run() -> None:
    asyncio.run(main())


if __name__ == "__main__":
    run()
