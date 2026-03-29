# GitHub Releases 监控系统

🔍 自动监控 GitHub 仓库版本发布，检测新版本并自动下载

---

## 📋 项目简介

本项目通过 shields.io 查询 GitHub 仓库最新 Release 版本，通过 xget 获取下载资产信息，通过 ghproxy 加速下载，与本地记录对比，发现新版本时自动下载并发送通知。

> 💡 由于中国大陆访问 GitHub 不稳定，采用 shields.io + xget + ghproxy 绕过限制

### 核心功能

- ✅ 读取 CSV 配置文件，批量监控多个仓库
- ✅ 通过 shields.io 获取最新 Release 版本（国内可访问）
- ✅ 通过 xget 获取下载资产（文件名、下载链接、sha256、大小）
- ✅ 通过 ghproxy 加速下载（国内可访问）
- ✅ SHA256 校验码自动验证，确保下载文件完整性
- ✅ 对比本地记录，检测新版本
- ✅ 发现新版本时自动下载所有资产文件
- ✅ 输出结构化 JSON 数据
- ✅ 使用 Unix 时间戳记录检查时间
- ✅ 429 速率限制自动处理（请求间隔 + 指数退避）
- 🔄 发现新版本时发送通知（待实现）

---

## 🗂️ 文件结构

```
/job/github/
├── github.csv           # 监控仓库配置
├── check_releases.py    # 主检查脚本
├── releases.json        # 最新版本数据输出
├── README.md            # 本说明文件
└── releases/            # 下载文件存储目录
    ├── tmp/             # 临时下载目录（sha256 作为文件名）
    └── {owner}/
        └── {repo}/
            └── {version}/
                └── {files}   # 完整文件名
```

### 下载目录示例

```
releases/
  microsoft/
    edit/
      v1.2.1/
        edit-1.2.0-aarch64-linux-gnu.tar.zst
        edit-1.2.0-x86_64-linux-gnu.tar.zst
        edit-1.2.1-aarch64-windows.zip
        edit-1.2.1-x86_64-windows.zip
  openclaw/
    openclaw/
      v2026.3.28/
        OpenClaw-2026.3.28.dmg
        OpenClaw-2026.3.28.zip
```

---

## 📦 环境要求

- **Python**: 3.12+（复用 `/job/py312/.venv`）
- **依赖**: 无额外依赖（使用标准库）

### 运行脚本

```bash
/job/py312/.venv/bin/python /job/github/check_releases.py
```

---

## 🔧 配置说明

### CSV 配置文件：`github.csv`

```csv
owner,repo,current_version,latest_version,last_checked
microsoft,edit,v1.2.1,v1.2.1,1774773371
openclaw,openclaw,v2026.3.28,v2026.3.28,1774773371
```

### 字段说明

| 字段 | 必填 | 更新方式 | 说明 |
|------|------|----------|------|
| `owner` | ✅ | 手动 | GitHub 用户名或组织名 |
| `repo` | ✅ | 手动 | 仓库名称 |
| `current_version` | ✅ | 手动 | 当前使用的版本号 |
| `latest_version` | ❌ | 自动 | GitHub 上最新发布版本 |
| `last_checked` | ❌ | 自动 | 上次检查时间（Unix 时间戳） |

### 版本对比逻辑

```
has_update = (latest_version != current_version) && (latest_version != "")
```

- `current_version` 为空时，视为首次检查，不触发更新通知和下载
- `latest_version` 与 `current_version` 不同时，标记为有更新并触发下载

---

## 📊 数据格式

### 输出文件：`releases.json`

```json
[
  {
    "owner": "microsoft",
    "repo": "edit",
    "latest_version": "v1.2.1",
    "current_version": "v1.0.0",
    "has_update": true,
    "html_url": "https://github.com/microsoft/edit/releases/tag/v1.2.1",
    "last_checked": 1774773371,
    "assets": [
      {
        "filename": "edit-1.2.1-x86_64-windows.zip",
        "download_url": "https://github.com/microsoft/edit/releases/download/v1.2.1/edit-1.2.1-x86_64-windows.zip",
        "sha256": "be3affb7e5e0cd856fc0fb9c8b2004e9fbbc364e69797f7c2e9d8fcc94bfc4ff",
        "size": "948 KB",
        "published_at": "2025-10-15T14:24:23Z"
      }
    ],
    "downloaded_assets": [
      {
        "filename": "edit-1.2.1-x86_64-windows.zip",
        "file_path": "/job/github/releases/microsoft/edit/v1.2.1/edit-1.2.1-x86_64-windows.zip",
        "sha256": "be3affb7e5e0cd856fc0fb9c8b2004e9fbbc364e69797f7c2e9d8fcc94bfc4ff",
        "file_size": 970468,
        "status": "downloaded"
      }
    ]
  }
]
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `owner` | string | 仓库所有者 |
| `repo` | string | 仓库名称 |
| `latest_version` | string | GitHub 上最新版本号 |
| `current_version` | string | 本地记录的版本号 |
| `has_update` | boolean | 是否有新版本 |
| `html_url` | string | Release 页面链接 |
| `last_checked` | integer | 检查时间（Unix 时间戳） |
| `assets` | array | 下载资产列表（可能为 null） |
| `downloaded_assets` | array | 已下载资产列表（仅在有更新时） |

### 资产字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `filename` | string | 文件名 |
| `download_url` | string | 下载链接（完整 URL） |
| `sha256` | string | SHA256 校验码 |
| `size` | string | 文件大小（如 "948 KB"） |
| `published_at` | string | 发布时间（ISO 8601） |

### 已下载资产字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `filename` | string | 文件名 |
| `file_path` | string | 本地文件完整路径 |
| `sha256` | string | SHA256 校验码（已验证） |
| `file_size` | integer | 文件大小（字节） |
| `status` | string | 状态：`downloaded` / `exists` / `failed` |

---

## 🔄 执行流程

```
┌─────────────────────────────────────────────────────────────┐
│  1. 初始化                                                   │
│     └─ 获取当前 Unix 时间戳                                  │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  2. 读取 CSV                                                 │
│     └─ 解析字段: owner, repo, current_version,               │
│                  latest_version, last_checked                │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  3. 遍历每个仓库                                             │
│     ├─ 请求间隔: 3 秒（避免 429）                             │
│     └─ Shields.io 获取最新版本号                              │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  4. 获取下载资产                                             │
│     ├─ Xget API: https://xget.xi-xu.me/gh/{owner}/{repo}/... │
│     ├─ 解析 HTML 提取资产信息                                 │
│     └─ 429 处理: Retry-After + 指数退避                       │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  5. 版本对比                                                 │
│     └─ has_update = (latest != current) && (latest != "")    │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  6. 下载资产文件（仅在有更新时）                               │
│     ├─ 创建目录: releases/{owner}/{repo}/{version}/           │
│     ├─ 使用 ghproxy 加速下载                                  │
│     ├─ 临时文件: releases/tmp/{sha256}                        │
│     ├─ SHA256 校验验证                                        │
│     └─ 移动到最终目录                                         │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  7. 保存结果                                                 │
│     ├─ releases.json: 完整检查结果 + 资产信息 + 下载状态       │
│     └─ github.csv: 更新 latest_version, last_checked         │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  8. 输出摘要                                                 │
│     ├─ 检查仓库数量                                          │
│     └─ 有更新的仓库列表 (old → new)                          │
└─────────────────────────────────────────────────────────────┘
```

---

## 🛠️ 使用指南

### 1. 检查所有仓库版本

```bash
/job/py312/.venv/bin/python /job/github/check_releases.py
```

### 2. 查看检查结果

```bash
cat /job/github/releases.json
```

### 3. 添加新仓库

编辑 `/job/github/github.csv`，添加一行：

```csv
owner,repo,current_version,latest_version,last_checked
newowner,newrepo,,, 
```

首次运行时 `current_version` 为空，不会触发下载。需要手动设置一个旧版本才会触发。

### 4. 更新本地版本

当你升级了某个软件后，手动更新 CSV 中的 `current_version`：

```csv
openclaw,openclaw,v2026.3.29,v2026.3.29,1774773371
```

### 5. 设置定时任务

```bash
# 每 6 小时检查一次（推荐）
0 */6 * * * /job/py312/.venv/bin/python /job/github/check_releases.py >> /job/github/cron.log 2>&1
```

---

## ⚙️ API 说明

### Shields.io - 获取版本号

```
GET https://img.shields.io/github/v/release/{owner}/{repo}
```

返回 SVG 图片，从 `<title>` 标签提取版本：

```html
<title>release: v1.2.1</title>
```

| 特点 | 说明 |
|------|------|
| ✅ 国内可访问 | 无需代理 |
| ✅ 无需认证 | 无速率限制 |
| ⚠️ 信息有限 | 仅返回版本号 |

### Xget - 获取下载资产

```
GET https://xget.xi-xu.me/gh/{owner}/{repo}/releases/expanded_assets/{version}
```

返回 HTML 页面，解析提取资产信息：

| 提取内容 | 说明 |
|----------|------|
| `filename` | 文件名 |
| `download_url` | 下载链接 |
| `sha256` | SHA256 校验码 |
| `size` | 文件大小 |
| `published_at` | 发布时间 |

| 特点 | 说明 |
|------|------|
| ✅ 国内可访问 | 无需代理 |
| ✅ 完整资产信息 | 包含下载链接和校验码 |
| ⚠️ 有速率限制 | 需控制请求频率 |

### Ghproxy - 加速下载

```
GET https://ghproxy.net/{original_github_url}
```

示例：

```
https://ghproxy.net/https://github.com/microsoft/edit/releases/download/v1.2.1/edit-1.2.1-x86_64-windows.zip
```

| 特点 | 说明 |
|------|------|
| ✅ 国内可访问 | 无需代理 |
| ✅ 支持大文件 | 稳定下载 |
| ✅ 保持原链接 | 校验码不变 |

---

## 🔐 文件校验流程

### SHA256 校验机制

```
┌────────────────────────────────────────────┐
│  1. 下载到临时目录 (tmp/{sha256})           │
└────────────────────────────────────────────┘
                    ↓
┌────────────────────────────────────────────┐
│  2. 计算下载文件的 SHA256                   │
└────────────────────────────────────────────┘
                    ↓
┌────────────────────────────────────────────┐
│  3. 对比预期校验码                          │
│     ├─ 匹配 → 移动到最终目录                │
│     └─ 不匹配 → 删除临时文件，报错          │
└────────────────────────────────────────────┘
                    ↓
┌────────────────────────────────────────────┐
│  4. 已存在文件检查                          │
│     ├─ 校验码匹配 → 跳过下载                │
│     └─ 校验码不匹配 → 重新下载              │
└────────────────────────────────────────────┘
```

---

## 🚨 错误处理

### 429 速率限制处理

| 措施 | 说明 |
|------|------|
| **请求间隔** | 每个仓库之间等待 3 秒 |
| **Retry-After** | 读取响应头，按服务器建议等待 |
| **指数退避** | 无 Retry-After 时：5s → 10s → 20s |
| **重试机制** | 最多 3 次重试 |

### 下载失败处理

| 措施 | 说明 |
|------|------|
| **重试机制** | 最多 3 次重试 |
| **SHA256 校验** | 校验失败自动删除临时文件 |
| **状态记录** | `downloaded_assets` 中记录 `status: failed` |

配置参数（脚本内）：

```python
REQUEST_DELAY = 3.0        # 请求间隔（秒）
retry_delay = 5.0          # 初始重试等待（秒）
max_retries = 3            # 最大重试次数
```

---

## 🔔 通知扩展（待实现）

支持的通知渠道：

- [ ] Telegram
- [ ] Discord
- [ ] 飞书
- [ ] 企业微信
- [ ] Webhook

---

## 📝 更新日志

### v1.3.0 (2026-03-29)

- ✨ 新增：自动下载资产文件（通过 ghproxy 加速）
- ✨ 新增：SHA256 校验码验证，确保下载文件完整性
- ✨ 新增：已存在文件自动跳过（校验码匹配时）
- ✨ 新增：`downloaded_assets` 字段记录下载状态
- 📝 更新：下载目录结构说明
- 📝 更新：执行流程图增加下载步骤

### v1.2.0 (2026-03-29)

- ✨ 新增：通过 xget 获取下载资产（文件名、下载链接、sha256、大小）
- ✨ 新增：CSV 增加 `latest_version` 字段
- ✨ 新增：429 速率限制自动处理（请求间隔 + 指数退避）

### v1.1.0 (2026-03-29)

- 改用 shields.io 查询版本（绕过中国大陆 GitHub API 限制）
- last_checked 改为 Unix 时间戳格式
- 移除 requests 依赖，使用标准库

### v1.0.0 (2026-03-29)

- 初始版本
- 支持 CSV 配置文件
- 支持版本对比和 JSON 输出

---

*最后更新：2026-03-29*
*版本：1.3.0*