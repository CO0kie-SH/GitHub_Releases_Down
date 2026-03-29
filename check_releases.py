#!/usr/bin/env python3
"""
GitHub Releases 监控脚本
通过 shields.io 查询 GitHub 仓库最新版本，与本地记录对比，输出 JSON 结果
"""

import csv
import json
import os
import re
import time
import hashlib
import shutil
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

# 配置
CSV_FILE = "/job/github/github.csv"
OUTPUT_FILE = "/job/github/releases.json"
SHIELDS_API = "https://img.shields.io/github/v/release"
XGET_API = "https://xget.xi-xu.me/gh"
GHPROXY_URL = "https://ghproxy.net"

# 目录配置
DOWNLOAD_DIR = "/job/github/releases"  # 下载目录
TMP_DIR = f"{DOWNLOAD_DIR}/tmp"        # 临时下载目录

# 请求间隔配置（避免 429 速率限制）
REQUEST_DELAY = 3.0  # 每个仓库之间的请求间隔（秒）

# GitHub Token（可选，用于直接 API 访问）
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN")


def get_release_assets_via_xget(owner: str, repo: str, version: str, max_retries: int = 3, retry_delay: float = 5.0) -> list[dict] | None:
    """通过 xget 获取 Release 的下载资产（文件名、下载链接、sha256、大小）"""
    url = f"{XGET_API}/{owner}/{repo}/releases/expanded_assets/{version}"
    headers = {
        "User-Agent": "OpenClaw-GitHub-Releases-Checker/1.0"
    }
    
    request = Request(url, headers=headers)
    
    for attempt in range(max_retries):
        try:
            with urlopen(request, timeout=30) as response:
                data = response.read().decode("utf-8")
                
                # 解析 HTML，提取资产信息
                assets = []
                # 匹配每个 <li> 中的资产信息
                li_pattern = r'<li[^>]*class="Box-row[^"]*"[^>]*>(.*?)</li>'
                li_matches = re.findall(li_pattern, data, re.DOTALL)
                
                for li_content in li_matches:
                    asset = {}
                    
                    # 提取文件名和下载链接
                    # <a href="/microsoft/edit/releases/download/v1.2.1/edit-1.2.1-x86_64-windows.zip">
                    a_match = re.search(r'<a href="([^"]+)"[^>]*>\s*<span[^>]*class="Truncate-text text-bold[^"]*"[^>]*>([^<]+)</span>', li_content)
                    if a_match:
                        relative_url = a_match.group(1)
                        asset["filename"] = a_match.group(2).strip()
                        # 拼接完整下载链接
                        asset["download_url"] = f"https://github.com{relative_url}"
                    
                    # 提取 sha256 校验码
                    # <span class="Truncate-text">sha256:xxx</span>
                    sha_match = re.search(r'sha256:([a-f0-9]{64})', li_content)
                    if sha_match:
                        asset["sha256"] = sha_match.group(1)
                    
                    # 提取文件大小
                    # <span ...>124 KB</span>
                    size_match = re.search(r'(\d+(?:\.\d+)?\s*[KMGT]?B)</span>', li_content)
                    if size_match:
                        asset["size"] = size_match.group(1)
                    
                    # 提取发布时间
                    # <relative-time datetime="2025-10-15T14:24:08Z">
                    time_match = re.search(r'datetime="([^"]+)"', li_content)
                    if time_match:
                        asset["published_at"] = time_match.group(1)
                    
                    # 只保留有下载链接的资产（排除源码压缩包）
                    if asset.get("download_url") and "archive/refs/tags" not in asset.get("download_url", ""):
                        assets.append(asset)
                
                if assets:
                    return assets
                else:
                    print(f"[WARN] {owner}/{repo}/{version}: No assets found (xget)")
                    return None
                    
        except HTTPError as e:
            if e.code == 429:
                # 速率限制，读取 Retry-After 或使用指数退避
                retry_after = e.headers.get("Retry-After")
                if retry_after:
                    wait_time = float(retry_after)
                else:
                    # 指数退避：每次重试等待时间加倍
                    wait_time = retry_delay * (2 ** attempt)
                print(f"[WARN] {owner}/{repo}/{version}: Rate limited (429), waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(wait_time)
                    continue
                return None
            else:
                print(f"[ERROR] {owner}/{repo}/{version}: HTTP {e.code} (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                return None
        except URLError as e:
            print(f"[ERROR] {owner}/{repo}/{version}: {e.reason} (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
                continue
            return None
        except Exception as e:
            print(f"[ERROR] {owner}/{repo}/{version}: {e}")
            return None
    
    return None


def calculate_sha256(file_path: str) -> str:
    """计算文件的 SHA256 校验码"""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def download_file(url: str, dest_path: str, expected_sha256: str = None, max_retries: int = 3) -> dict:
    """下载文件到指定路径，可选校验 SHA256"""
    headers = {
        "User-Agent": "OpenClaw-GitHub-Releases-Checker/1.0"
    }
    
    # 确保目标目录存在
    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
    
    for attempt in range(max_retries):
        try:
            request = Request(url, headers=headers)
            with urlopen(request, timeout=60) as response:
                # 写入文件
                with open(dest_path, "wb") as f:
                    while True:
                        chunk = response.read(8192)
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
            
        except HTTPError as e:
            print(f"[ERROR] Download failed: HTTP {e.code} (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return {"success": False, "error": f"HTTP {e.code}"}
        except URLError as e:
            print(f"[ERROR] Download failed: {e.reason} (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return {"success": False, "error": str(e.reason)}
        except Exception as e:
            print(f"[ERROR] Download failed: {e} (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return {"success": False, "error": str(e)}
    
    return {"success": False, "error": "Max retries exceeded"}


def download_assets(owner: str, repo: str, version: str, assets: list[dict], only_new: bool = True) -> list[dict]:
    """下载所有资产文件"""
    if not assets:
        return []
    
    # 创建目录结构: releases/owner/repo/version/
    version_dir = f"{DOWNLOAD_DIR}/{owner}/{repo}/{version}"
    os.makedirs(version_dir, exist_ok=True)
    os.makedirs(TMP_DIR, exist_ok=True)
    
    downloaded = []
    
    for asset in assets:
        filename = asset.get("filename")
        download_url = asset.get("download_url")
        expected_sha256 = asset.get("sha256")
        
        if not filename or not download_url:
            continue
        
        # 目标文件路径
        final_path = f"{version_dir}/{filename}"
        
        # 检查文件是否已存在且校验码正确
        if os.path.exists(final_path) and expected_sha256:
            actual_sha256 = calculate_sha256(final_path)
            if actual_sha256 == expected_sha256:
                print(f"[INFO] File already exists and verified: {filename}")
                downloaded.append({
                    "filename": filename,
                    "file_path": final_path,
                    "sha256": actual_sha256,
                    "status": "exists"
                })
                continue
        
        # 使用 ghproxy 镜像加速下载
        proxy_url = f"{GHPROXY_URL}/{download_url}"
        
        # 临时文件路径（使用 sha256 作为文件名）
        tmp_path = f"{TMP_DIR}/{expected_sha256}" if expected_sha256 else f"{TMP_DIR}/{filename}.tmp"
        
        print(f"[INFO] Downloading {filename} via ghproxy...")
        result = download_file(proxy_url, tmp_path, expected_sha256)
        
        if result.get("success"):
            # 移动到最终目录
            shutil.move(tmp_path, final_path)
            downloaded.append({
                "filename": filename,
                "file_path": final_path,
                "sha256": result.get("sha256"),
                "file_size": result.get("file_size"),
                "status": "downloaded"
            })
            print(f"[INFO] Downloaded and verified: {filename}")
        else:
            # 清理临时文件
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            downloaded.append({
                "filename": filename,
                "status": "failed",
                "error": result.get("error")
            })
            print(f"[ERROR] Failed to download: {filename} - {result.get('error')}")
    
    return downloaded


def get_latest_release_via_shields(owner: str, repo: str, max_retries: int = 3) -> dict | None:
    """通过 shields.io 获取仓库的最新 Release 版本"""
    url = f"{SHIELDS_API}/{owner}/{repo}"
    headers = {
        "User-Agent": "OpenClaw-GitHub-Releases-Checker/1.0"
    }
    
    request = Request(url, headers=headers)
    
    for attempt in range(max_retries):
        try:
            with urlopen(request, timeout=30) as response:
                data = response.read().decode("utf-8")
                
                # 从 SVG 中提取 title 标签内容
                # 格式: <title>release: v1.2.1</title>
                match = re.search(r'<title>([^<]+)</title>', data)
                if match:
                    title = match.group(1)
                    # 解析 "release: v1.2.1" 或 "release: none" 等格式
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
                    
        except HTTPError as e:
            print(f"[ERROR] {owner}/{repo}: HTTP {e.code} (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return None
        except URLError as e:
            print(f"[ERROR] {owner}/{repo}: {e.reason} (attempt {attempt + 1}/{max_retries})")
            if attempt < max_retries - 1:
                time.sleep(2)
                continue
            return None
        except Exception as e:
            print(f"[ERROR] {owner}/{repo}: {e}")
            return None
    
    return None


def read_csv() -> list[dict]:
    """读取 CSV 配置文件"""
    repos = []
    if not os.path.exists(CSV_FILE):
        print(f"[ERROR] CSV file not found: {CSV_FILE}")
        return repos
    
    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            repos.append({
                "owner": row.get("owner", "").strip(),
                "repo": row.get("repo", "").strip(),
                "current_version": row.get("current_version", "").strip(),
                "latest_version": row.get("latest_version", "").strip(),
                "last_checked": row.get("last_checked", "").strip()
            })
    
    return repos


def write_csv(repos: list[dict]) -> None:
    """更新 CSV 文件"""
    with open(CSV_FILE, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["owner", "repo", "current_version", "latest_version", "last_checked"])
        writer.writeheader()
        for repo in repos:
            writer.writerow({
                "owner": repo["owner"],
                "repo": repo["repo"],
                "current_version": repo["current_version"],
                "latest_version": repo.get("latest_version", ""),
                "last_checked": repo.get("last_checked", "")
            })


def main():
    """主函数"""
    now_timestamp = int(time.time())
    print(f"[INFO] Starting GitHub releases check at timestamp {now_timestamp}")
    
    repos = read_csv()
    if not repos:
        print("[WARN] No repositories to check")
        return
    
    results = []
    updates_found = []
    
    for i, repo in enumerate(repos):
        owner = repo["owner"]
        repo_name = repo["repo"]
        current_version = repo["current_version"]
        
        # 请求间隔：非首个仓库前等待，避免 429
        if i > 0:
            print(f"[INFO] Waiting {REQUEST_DELAY}s before next request...")
            time.sleep(REQUEST_DELAY)
        
        print(f"[INFO] Checking {owner}/{repo_name}...")
        
        release = get_latest_release_via_shields(owner, repo_name)
        
        if release is None:
            # 获取失败，仍然记录
            result = {
                "owner": owner,
                "repo": repo_name,
                "latest_version": None,
                "current_version": current_version,
                "has_update": False,
                "published_at": None,
                "html_url": f"https://github.com/{owner}/{repo_name}/releases",
                "last_checked": now_timestamp,
                "assets": None,
                "error": "Failed to fetch release info"
            }
        else:
            latest_version = release["tag_name"]
            has_update = latest_version != current_version and latest_version != ""
            
            # 获取下载资产
            print(f"[INFO] Fetching assets for {owner}/{repo_name}/{latest_version}...")
            assets = get_release_assets_via_xget(owner, repo_name, latest_version)
            
            # 下载资产文件（仅在有更新时下载）
            downloaded_assets = None
            if assets and has_update:
                print(f"[INFO] Downloading assets for {owner}/{repo_name}/{latest_version}...")
                downloaded_assets = download_assets(owner, repo_name, latest_version, assets)
            
            result = {
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
            
            if has_update:
                updates_found.append({
                    "owner": owner,
                    "repo": repo_name,
                    "old_version": current_version,
                    "new_version": latest_version,
                    "assets": assets,
                    "downloaded_assets": downloaded_assets
                })
            
            # 更新 CSV 中的 latest_version 和 last_checked
            repo["latest_version"] = latest_version
            repo["last_checked"] = str(now_timestamp)
        
        results.append(result)
    
    # 保存结果
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    
    print(f"[INFO] Results saved to {OUTPUT_FILE}")
    
    # 更新 CSV（更新检查时间）
    write_csv(repos)
    
    # 输出摘要
    print(f"\n[SUMMARY] Checked {len(repos)} repositories")
    if updates_found:
        print(f"[UPDATES] {len(updates_found)} new version(s) found:")
        for u in updates_found:
            print(f"  - {u['owner']}/{u['repo']}: {u['old_version']} → {u['new_version']}")
    else:
        print("[UPDATES] No new versions found")


if __name__ == "__main__":
    main()