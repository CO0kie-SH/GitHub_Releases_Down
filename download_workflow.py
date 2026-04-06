#!/usr/bin/env python3
"""
Download workflow module.

Step 8: download release assets when updates are found.
Step 9-11: persist results, print summary, send Feishu notifications.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Callable

import aiohttp

from feishu_notifier import send_feishu_message


class DownloadWorkflow:
    """Handle download and post-processing workflow."""

    def __init__(self, logger=None):
        self.logger = logger

    async def download_assets(
        self,
        session: aiohttp.ClientSession,
        tag: str,
        owner: str,
        repo_name: str,
        version: str,
        assets: list[dict],
        download_dir: Path,
        tmp_dir: Path,
        ghproxy_url: str,
        calculate_sha256_func: Callable[[str], str],
        download_file_func: Callable[[aiohttp.ClientSession, str, str, str | None], Any],
    ) -> list[dict]:
        if not assets:
            return []

        if tag:
            version_dir = download_dir / f"0{tag}" / owner / repo_name / version
        else:
            version_dir = download_dir / owner / repo_name / version

        version_dir.mkdir(parents=True, exist_ok=True)
        tmp_dir.mkdir(parents=True, exist_ok=True)

        downloaded: list[dict] = []

        for asset in assets:
            filename = asset.get("filename")
            download_url = asset.get("download_url")
            expected_sha256 = asset.get("sha256")

            if not filename or not download_url:
                continue

            final_path = version_dir / filename
            existing_sha256 = None

            if final_path.exists():
                try:
                    existing_sha256 = calculate_sha256_func(str(final_path))
                except Exception as e:
                    if self.logger:
                        self.logger.warning(f"Failed to calculate existing file sha256 for {final_path}: {e}")

            meta_msg = (
                f"Download meta | url={download_url} | expected_sha256={expected_sha256 or 'N/A'} "
                f"| target_path={final_path} | existing_sha256={existing_sha256 or 'N/A'}"
            )
            if self.logger:
                self.logger.info(meta_msg)
            else:
                print(meta_msg)

            if final_path.exists():
                if expected_sha256:
                    actual_sha256 = calculate_sha256_func(str(final_path))
                    if actual_sha256 == expected_sha256:
                        downloaded.append(
                            {
                                "filename": filename,
                                "file_path": str(final_path),
                                "sha256": actual_sha256,
                                "status": "exists",
                            }
                        )
                        if self.logger:
                            self.logger.info(f"File already exists and verified: {filename}")
                        continue
                else:
                    if self.logger:
                        self.logger.info(f"File already exists (no sha256 provided): {filename}")
                    downloaded.append(
                        {
                            "filename": filename,
                            "file_path": str(final_path),
                            "sha256": None,
                            "status": "exists",
                        }
                    )
                    continue

            proxy_url = f"{ghproxy_url}/{download_url}"
            tmp_path = tmp_dir / (expected_sha256 if expected_sha256 else f"{filename}.tmp")

            if self.logger:
                self.logger.info(f"Downloading {filename} via ghproxy...")

            result = await download_file_func(session, proxy_url, str(tmp_path), expected_sha256)

            if result.get("success"):
                shutil.move(str(tmp_path), str(final_path))
                downloaded.append(
                    {
                        "filename": filename,
                        "file_path": str(final_path),
                        "sha256": result.get("sha256"),
                        "file_size": result.get("file_size"),
                        "status": "downloaded",
                    }
                )
                if self.logger:
                    self.logger.info(f"Downloaded and verified: {filename}")
            else:
                if tmp_path.exists():
                    tmp_path.unlink()
                downloaded.append(
                    {
                        "filename": filename,
                        "status": "failed",
                        "error": result.get("error"),
                    }
                )
                if self.logger:
                    self.logger.error(f"Failed to download: {filename} - {result.get('error')}")

        return downloaded

    async def download_assets_if_needed(
        self,
        session: aiohttp.ClientSession,
        tag: str,
        owner: str,
        repo_name: str,
        latest_version: str,
        assets: list[dict] | None,
        has_update: bool,
        download_assets_func: Callable[[aiohttp.ClientSession, str, str, str, str, list[dict]], Any],
        download_assets_kwargs: dict | None = None,
    ) -> list[dict] | None:
        downloaded_assets = None
        if assets and has_update:
            if self.logger:
                self.logger.info(f"Downloading assets for {owner}/{repo_name}/{latest_version}...")
            extra_kwargs = download_assets_kwargs or {}
            downloaded_assets = await download_assets_func(
                session,
                tag,
                owner,
                repo_name,
                latest_version,
                assets,
                **extra_kwargs,
            )
        return downloaded_assets

    async def persist_and_notify(
        self,
        output_file: Path,
        results: list[dict],
        repos: list[dict],
        updates_found: list[dict],
        write_csv_func: Callable[[list[dict]], None],
    ) -> None:
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        if self.logger:
            self.logger.info(f"Results saved to {output_file}")

        write_csv_func(repos)

        print(f"\n[SUMMARY] Checked {len(repos)} repositories")
        if not updates_found:
            print("[UPDATES] No new versions found")
            return

        print(f"[UPDATES] {len(updates_found)} new version(s) found:")
        for update in updates_found:
            tag_str = f"[{update['tag']}] " if update["tag"] else ""
            print(
                f"  - {tag_str}{update['owner']}/{update['repo']}: "
                f"{update['old_version']} -> {update['new_version']}"
            )

        try:
            message_lines = [f"发现 {len(updates_found)} 个更新:"]
            for update in updates_found:
                tag_str = f"[{update['tag']}] " if update["tag"] else ""
                message_lines.append(
                    f"{tag_str}{update['owner']}/{update['repo']}: "
                    f"{update['old_version']} -> {update['new_version']}"
                )

                downloaded_assets = update.get("downloaded_assets", [])
                if downloaded_assets:
                    message_lines.append("  下载文件:")
                    for asset in downloaded_assets:
                        if asset.get("status") == "downloaded":
                            filename = asset.get("filename", "")
                            size = asset.get("file_size", 0)
                            size_mb = size / (1024 * 1024) if size else 0
                            message_lines.append(f"    - {filename} ({size_mb:.2f} MB)")

            message_body = "\n".join(message_lines)
            print("[FLOW] Sending Feishu notification...")
            await send_feishu_message(self.logger, message_body, v_title="GITHUB订阅更新")
        except Exception as e:
            if self.logger:
                self.logger.error(f"发送飞书通知失败: {e}")


# Backward-compatible function wrappers
async def download_assets(*args, logger=None, **kwargs):
    return await DownloadWorkflow(logger=logger).download_assets(*args, **kwargs)


async def download_assets_if_needed(*args, logger=None, **kwargs):
    return await DownloadWorkflow(logger=logger).download_assets_if_needed(*args, **kwargs)


async def persist_and_notify(*args, logger=None, **kwargs):
    return await DownloadWorkflow(logger=logger).persist_and_notify(*args, **kwargs)
