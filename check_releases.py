#!/usr/bin/env python3
"""
GitHub Releases 监控脚本 (异步版本)
通过 shields.io 查询 GitHub 仓库最新版本，与本地记录对比，输出 JSON 结果
使用 aiohttp 实现异步网络请求
"""

import csv
import json
import os
import re
import time
import hashlib
import shutil
import asyncio
import aiohttp
import logging
from pathlib import Path
from datetime import datetime, timedelta

# 获取脚本所在目录（支持软链接）
SCRIPT_DIR = Path(__file__).parent.resolve()
if Path(__file__).is_symlink():
    SCRIPT_DIR = Path(__file__).resolve().parent

# 配置（相对于脚本目录）
CSV_FILE = SCRIPT_DIR / "github.csv"
OUTPUT_FILE = SCRIPT_DIR / "releases.json"
SHIELDS_API = "https://img.shields.io/github/v/release"
XGET_API = "https://xget.xi-xu.me/gh"
GHPROXY_URL = "https://ghproxy.net"

# 目录配置（相对于脚本目录）
DOWNLOAD_DIR = SCRIPT_DIR / "releases"
TMP_DIR = SCRIPT_DIR / "tmp"
LOG_DIR = SCRIPT_DIR / "log"
DB_DIR = SCRIPT_DIR / "db"

# 获取 logger（由 main.py 初始化）
logger = logging.getLogger(__name__)


def clean_old_logs(log_dir: Path, days: int = 30):
    """清理超过指定天数的旧日志文件"""
    try:
        cutoff_date = datetime.now() - timedelta(days=days)
        for log_file in log_dir.glob("*.log"):
            if log_file.is_file():
                file_mtime = datetime.fromtimestamp(log_file.stat().st_mtime)
                if file_mtime < cutoff_date:
                    log_file.unlink()
                    logger.info(f"已删除旧日志文件: {log_file.name}")
    except Exception as e:
        logger.error(f"清理旧日志文件时出错: {e}")


# 请求间隔配置（避免 429 速率限制）
REQUEST_DELAY = 3.0  # 每个仓库之间的请求间隔（秒）

# GitHub Token（可选，用于直接 API 访问）
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")


async def get_release_assets_via_xget(
    session: aiohttp.ClientSession,
    owner: str,
    repo: str,
    version: str,
    max_retries: int = 3,
    retry_delay: float = 5.0
) -> list[dict] | None:
    """通过 xget 获取 Release 的下载资产（异步版本）
    
    Args:
        session: aiohttp 会话
        owner: 仓库所有者
        repo: 仓库名称
        version: 版本号（尝试两种格式：带 v 和不带 v）
        max_retries: 最大重试次数（仅针对 429）
        retry_delay: 初始重试等待时间
    """
    # 两种版本格式都尝试：带 v 和不带 v
    versions_to_try = [version, version.lstrip('v')]
    # 如果两个版本相同，只尝试一次
    if versions_to_try[0] == versions_to_try[1]:
        versions_to_try = [version]
    
    for xget_version in versions_to_try:
        url = f"{XGET_API}/{owner}/{repo}/releases/expanded_assets/{xget_version}"
        
        for attempt in range(max_retries):
            try:
                async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                    if response.status == 429:
                        # 速率限制，重试
                        retry_after = response.headers.get("Retry-After")
                        wait_time = float(retry_after) if retry_after else retry_delay * (2 ** attempt)
                        print(f"[WARN] {owner}/{repo}/{xget_version}: HTTP 429, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                        if attempt < max_retries - 1:
                            await asyncio.sleep(wait_time)
                            continue
                        # 重试次数用完，尝试下一个版本格式
                        break
                    
                    if response.status == 404:
                        # 资产不存在，尝试下一个版本格式（不重试）
                        break
                    
                    if response.status != 200:
                        print(f"[ERROR] {owner}/{repo}/{xget_version}: HTTP {response.status}")
                        break
                    
                    data = await response.text()
                    
                    # 解析 HTML，提取资产信息
                    assets = []
                    li_pattern = r'<li[^>]*class="Box-row[^"]*"[^>]*>(.*?)</li>'
                    li_matches = re.findall(li_pattern, data, re.DOTALL)
                    
                    for li_content in li_matches:
                        asset = {}
                        
                        # 提取文件名和下载链接
                        a_match = re.search(
                            r'<a href="([^"]+)"[^>]*>\s*<span[^>]*class="Truncate-text text-bold[^"]*"[^>]*>([^<]+)</span>',
                            li_content
                        )
                        if a_match:
                            relative_url = a_match.group(1)
                            asset["filename"] = a_match.group(2).strip()
                            asset["download_url"] = f"https://github.com{relative_url}"
                        
                        # 提取 sha256 校验码
                        sha_match = re.search(r'sha256:([a-f0-9]{64})', li_content)
                        if sha_match:
                            asset["sha256"] = sha_match.group(1)
                        
                        # 提取文件大小
                        size_match = re.search(r'(\d+(?:\.\d+)?\s*[KMGT]?B)</span>', li_content)
                        if size_match:
                            asset["size"] = size_match.group(1)
                        
                        # 提取发布时间
                        time_match = re.search(r'datetime="([^"]+)"', li_content)
                        if time_match:
                            asset["published_at"] = time_match.group(1)
                        
                        # 只保留有下载链接的资产（排除源码压缩包）
                        if asset.get("download_url") and "archive/refs/tags" not in asset.get("download_url", ""):
                            assets.append(asset)
                    
                    if assets:
                        return assets
                    # 没找到资产，尝试下一个版本格式
                    break
                        
            except asyncio.TimeoutError:
                print(f"[ERROR] {owner}/{repo}/{xget_version}: Timeout (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
                break
            except aiohttp.ClientError as e:
                print(f"[ERROR] {owner}/{repo}/{xget_version}: {e} (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    await asyncio.sleep(retry_delay)
                    continue
                break
            except Exception as e:
                print(f"[ERROR] {owner}/{repo}/{xget_version}: {e}")
                break
        
        # 如果成功获取到资产，直接返回
        # 否则继续尝试下一个版本格式
    
    print(f"[WARN] {owner}/{repo}/{version}: No assets found (xget)")
    return None


async def get_latest_release_via_shields(
    session: aiohttp.ClientSession,
    owner: str,
    repo: str,
    max_retries: int = 3
) -> dict | None:
    """通过 shields.io 获取仓库的最新 Release 版本（异步版本）"""
    url = f"{SHIELDS_API}/{owner}/{repo}"
    
    for attempt in range(max_retries):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as response:
                if response.status == 429:
                    retry_after = response.headers.get("Retry-After")
                    wait_time = float(retry_after) if retry_after else 5.0 * (2 ** attempt)
                    print(f"[WARN] {owner}/{repo}: HTTP 429, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(wait_time)
                        continue
                    return None
                
                if response.status != 200:
                    print(f"[ERROR] {owner}/{repo}: HTTP {response.status} (attempt {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)
                        continue
                    return None
                
                data = await response.text()
                
                # 从 SVG 中提取 title 标签内容
                match = re.search(r'<title>([^<]+)</title>', data)
                if match:
                    title = match.group(1)
                    if ":" in title:
                        version = title.split(":", 1)[1].strip()
                        if version and version.lower() not in ("none", "no releases"):
                            return {
                                "tag_name": version,
                                "source": "shields.io"
                            }
                        else:
                            print(f"[WARN] {owner}/{repo}: No releases found (shields.io)")
                            return None
                    else:
                        print(f"[WARN] {owner}/{repo}: Unexpected title format: {title}")
                        return None
                else:
                    print(f"[WARN] {owner}/{repo}: No title found in SVG")
                    return None
                    
        except asyncio.TimeoutError:
            print(f"[ERROR] {owner}/{repo}: Timeout (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
                continue
            return None
        except aiohttp.ClientError as e:
            print(f"[ERROR] {owner}/{repo}: {e} (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
                continue
            return None
        except Exception as e:
            print(f"[ERROR] {owner}/{repo}: {e}")
            return None
    
    return None


def calculate_sha256(file_path: str) -> str:
    """计算文件的 SHA256 校验码"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


async def download_file(
    session: aiohttp.ClientSession,
    url: str,
    dest_path: str,
    expected_sha256: str = None,
    max_retries: int = 3
) -> dict:
    """下载文件到指定路径（异步版本）"""
    # 确保目标目录存在
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    
    for attempt in range(max_retries):
        try:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=120)) as response:
                if response.status == 429:
                    retry_after = response.headers.get("Retry-After")
                    wait_time = float(retry_after) if retry_after else 5.0 * (2 ** attempt)
                    print(f"[WARN] Download: HTTP 429, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(wait_time)
                        continue
                    return {"success": False, "error": "HTTP 429"}
                
                if response.status != 200:
                    print(f"[ERROR] Download failed: HTTP {response.status} (attempt {attempt + 1}/{max_retries})")
                    if attempt < max_retries - 1:
                        await asyncio.sleep(2)
                        continue
                    return {"success": False, "error": f"HTTP {response.status}"}
                
                # 写入文件
                with open(dest_path, "wb") as f:
                    while True:
                        chunk = await response.content.read(8192)
                        if not chunk:
                            break
                        f.write(chunk)
            
            # 校验 SHA256
            if expected_sha256:
                actual_sha256 = calculate_sha256(dest_path)
                if actual_sha256 != expected_sha256:
                    print(f"[ERROR] SHA256 mismatch: expected {expected_sha256}, got {actual_sha256}")
                    os.remove(dest_path)
                    return {
                        "success": False,
                        "error": "SHA256 mismatch",
                        "expected_sha256": expected_sha256,
                        "actual_sha256": actual_sha256
                    }
            
            file_size = os.path.getsize(dest_path)
            return {
                "success": True,
                "file_path": dest_path,
                "file_size": file_size,
                "sha256": expected_sha256 or calculate_sha256(dest_path)
            }
            
        except asyncio.TimeoutError:
            print(f"[ERROR] Download timeout (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
                continue
            return {"success": False, "error": "Timeout"}
        except aiohttp.ClientError as e:
            print(f"[ERROR] Download failed: {e} (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
                continue
            return {"success": False, "error": str(e)}
        except Exception as e:
            print(f"[ERROR] Download failed: {e} (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                await asyncio.sleep(2)
                continue
            return {"success": False, "error": str(e)}
    
    return {"success": False, "error": "Max retries exceeded"}


async def download_assets(
    session: aiohttp.ClientSession,
    tag: str,
    owner: str,
    repo: str,
    version: str,
    assets: list[dict]
) -> list[dict]:
    """下载所有资产文件（异步版本）
    
    Args:
        session: aiohttp 会话
        tag: 分类标签，非空时目录结构为 releases/0{tag}/{owner}/{repo}/{version}/
        owner: 仓库所有者
        repo: 仓库名称
        version: 版本号
        assets: 资产列表
    """
    if not assets:
        return []
    
    # 根据 tag 决定目录结构
    if tag:
        version_dir = DOWNLOAD_DIR / f"0{tag}" / owner / repo / version
    else:
        version_dir = DOWNLOAD_DIR / owner / repo / version
    
    version_dir.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)
    
    downloaded = []
    
    for asset in assets:
        filename = asset.get("filename")
        download_url = asset.get("download_url")
        expected_sha256 = asset.get("sha256")
        
        if not filename or not download_url:
            continue
        
        final_path = version_dir / filename
        
        # 检查文件是否已存在且校验码正确
        if final_path.exists() and expected_sha256:
            actual_sha256 = calculate_sha256(str(final_path))
            if actual_sha256 == expected_sha256:
                print(f"[INFO] File already exists and verified: {filename}")
                downloaded.append({
                    "filename": filename,
                    "file_path": str(final_path),
                    "sha256": actual_sha256,
                    "status": "exists"
                })
                continue
        
        # 使用 ghproxy 镜像加速下载
        proxy_url = f"{GHPROXY_URL}/{download_url}"
        
        # 临时文件路径
        tmp_path = TMP_DIR / (expected_sha256 if expected_sha256 else f"{filename}.tmp")
        
        print(f"[INFO] Downloading {filename} via ghproxy...")
        result = await download_file(session, proxy_url, str(tmp_path), expected_sha256)
        
        if result.get("success"):
            shutil.move(str(tmp_path), str(final_path))
            downloaded.append({
                "filename": filename,
                "file_path": str(final_path),
                "sha256": result.get("sha256"),
                "file_size": result.get("file_size"),
                "status": "downloaded"
            })
            print(f"[INFO] Downloaded and verified: {filename}")
        else:
            if tmp_path.exists():
                tmp_path.unlink()
            downloaded.append({
                "filename": filename,
                "status": "failed",
                "error": result.get("error")
            })
            print(f"[ERROR] Failed to download: {filename} - {result.get('error')}")
    
    return downloaded


def read_csv() -> list[dict]:
    """读取 CSV 配置文件"""
    repos = []
    if not CSV_FILE.exists():
        print(f"[ERROR] CSV file not found: {CSV_FILE}")
        return repos
    
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            repos.append({
                "tag": (row.get("tag") or "").strip(),
                "owner": (row.get("owner") or "").strip(),
                "repo": (row.get("repo") or "").strip(),
                "current_version": (row.get("current_version") or "").strip(),
                "latest_version": (row.get("latest_version") or "").strip(),
                "last_checked": (row.get("last_checked") or "").strip()
            })
    
    return repos


def write_csv(repos: list[dict]) -> None:
    """更新 CSV 文件"""
    with open(CSV_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["tag", "owner", "repo", "current_version", "latest_version", "last_checked"])
        writer.writeheader()
        for repo in repos:
            writer.writerow({
                "tag": repo.get("tag", ""),
                "owner": repo["owner"],
                "repo": repo["repo"],
                "current_version": repo["current_version"],
                "latest_version": repo.get("latest_version", ""),
                "last_checked": repo.get("last_checked", "")
            })


async def check_repo(
    session: aiohttp.ClientSession,
    repo: dict,
    index: int,
    now_timestamp: int
) -> dict:
    """检查单个仓库（异步）"""
    tag = repo["tag"]
    owner = repo["owner"]
    repo_name = repo["repo"]
    current_version = repo["current_version"]
    
    # 请求间隔
    if index > 0:
        print(f"[INFO] Waiting {REQUEST_DELAY}s before next request...")
        await asyncio.sleep(REQUEST_DELAY)
    
    print(f"[INFO] Checking {owner}/{repo_name}...")
    
    release = await get_latest_release_via_shields(session, owner, repo_name)
    
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
            "error": "Failed to fetch release info"
        }
    
    latest_version = release["tag_name"]
    has_update = latest_version != current_version and latest_version != ""
    
    # 获取下载资产
    print(f"[INFO] Fetching assets for {owner}/{repo_name}/{latest_version}...")
    assets = await get_release_assets_via_xget(session, owner, repo_name, latest_version)
    
    # 下载资产文件（仅在有更新时下载）
    downloaded_assets = None
    if assets and has_update:
        print(f"[INFO] Downloading assets for {owner}/{repo_name}/{latest_version}...")
        downloaded_assets = await download_assets(session, tag, owner, repo_name, latest_version, assets)
    
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
        "downloaded_assets": downloaded_assets
    }
    
    # 更新 repo 字典
    repo["latest_version"] = latest_version
    repo["last_checked"] = str(now_timestamp)
    
    return result


async def main():
    """主函数（异步）"""
    now_timestamp = int(time.time())
    print(f"[INFO] Starting GitHub releases check at timestamp {now_timestamp}")
    
    repos = read_csv()
    if not repos:
        print("[WARN] No repositories to check")
        return
    
    results = []
    updates_found = []
    
    # 创建 aiohttp 会话
    headers = {
        "User-Agent": "OpenClaw-GitHub-Releases-Checker/1.0"
    }
    
    async with aiohttp.ClientSession(headers=headers) as session:
        # 顺序检查每个仓库（保持请求间隔）
        for i, repo in enumerate(repos):
            result = await check_repo(session, repo, i, now_timestamp)
            results.append(result)
            
            if result.get("has_update"):
                updates_found.append({
                    "tag": result["tag"],
                    "owner": result["owner"],
                    "repo": result["repo"],
                    "old_version": result["current_version"],
                    "new_version": result["latest_version"],
                    "assets": result.get("assets"),
                    "downloaded_assets": result.get("downloaded_assets")
                })
    
    # 保存结果
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"[INFO] Results saved to {OUTPUT_FILE}")
    
    # 更新 CSV
    write_csv(repos)
    
    # 输出摘要
    print(f"\n[SUMMARY] Checked {len(repos)} repositories")
    if updates_found:
        print(f"[UPDATES] {len(updates_found)} new version(s) found:")
        for u in updates_found:
            tag_str = f"[{u['tag']}] " if u['tag'] else ""
            print(f"  - {tag_str}{u['owner']}/{u['repo']}: {u['old_version']} → {u['new_version']}")
    else:
        print("[UPDATES] No new versions found")


def run():
    """入口函数"""
    asyncio.run(main())


if __name__ == "__main__":
    run()