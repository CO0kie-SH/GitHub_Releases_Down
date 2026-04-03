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
- ✅ **异步网络请求**：使用 aiohttp 实现高效并发
- ✅ **tag 分类功能**：支持按标签分类存储下载文件
- ✅ **版本格式兼容**：自动尝试带 v 和不带 v 的版本格式
- ✅ **429 速率限制处理**：自动重试 + 指数退避
- ✅ 输出结构化 JSON 数据
- ✅ 使用 Unix 时间戳记录检查时间
- 🔄 发现新版本时发送通知（待实现）

---

## 🗂️ 文件结构

```
github/                         # 脚本所在目录（相对路径）
├── github.csv                  # 监控仓库配置
├── check_releases.py           # 主检查脚本（异步版本）
├── main.py                     # 入口脚本（PyCharm）
├── releases.json               # 最新版本数据输出
├── README.md                   # 本说明文件
└── releases/                   # 下载文件存储目录
    ├── tmp/                    # 临时下载目录（sha256 作为文件名）
    ├── {owner}/                # 无 tag 的仓库
    │   └── {repo}/
    │       └── {version}/
    │           └── {files}
    └── 0{tag}/                 # 有 tag 的仓库
        └── {owner}/
            └── {repo}/
                └── {version}/
                    └── {files}
```

### 下载目录示例

```
releases/
  microsoft/                    # 无 tag
    edit/
      v1.2.1/
        edit-1.2.0-aarch64-linux-gnu.tar.zst
        edit-1.2.1-x86_64-windows.zip
  0android/                     # tag=android
    gkd-kit/
      gkd/
        v1.11.6/
          gkd-v1.11.6.apk
          outputs-v1.11.6.zip
  0clash/                       # tag=clash
    Clash-Verge-rev/
      clash-verge-rev/
        v2.4.7/
          Clash Verge_2.4.7_x64_fixed_webview2-setup.exe
          Clash Verge_2.4.7_arm64_fixed_webview2-setup.exe
          Clash.Verge_2.4.7_x64.dmg
          Clash.Verge_2.4.7_aarch64.dmg
          Clash Verge_2.4.7_amd64.deb
          Clash Verge_2.4.7_arm64.deb
          ... (更多平台支持)
  0xposed/                      # tag=xposed
    shatyuka/
      Zhiliao/
        v26.02.03/
          Zhiliao_26.02.03.apk
    Dr-TSNG/
      ZygiskNext/
        v1.3.3/
          Zygisk-Next-1.3.3-731-1193e46-release.zip
    yujincheng08/
      BiliRoaming/
        v1.7.0/
          BiliRoaming_1.7.0.apk
  0python/                      # tag=python
    astral-sh/
      uv/
        v0.11.3/
          uv-x86_64-pc-windows-msvc.zip
          uv-x86_64-apple-darwin.tar.gz
          uv-x86_64-unknown-linux-gnu.tar.gz
          source.tar.gz
          dist-manifest.json
          sha256.sum
          ... (更多平台支持)
  0network/                     # tag=network
    zhongyang219/
      TrafficMonitor/
        V1.86/
          TrafficMonitor_V1.86_x64.zip
          TrafficMonitor_V1.86_x64_Lite.zip
          TrafficMonitor_V1.86_x86.zip
          TrafficMonitor_V1.86_x86_Lite.zip
          TrafficMonitor_V1.86_arm64ec.zip
          TrafficMonitor_V1.86_arm64ec_Lite.zip
```

---

## 📦 环境要求

- **Python**: 3.12+
- **依赖**: 
  - `aiohttp` - 异步 HTTP 客户端

### 安装依赖

```bash
pip install aiohttp

# 或使用国内镜像
pip install aiohttp -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 运行脚本

```bash
# Windows 系统
cmd /c "set PYTHONIOENCODING=utf-8 && set path=D:\0code\py312;D:\job\py312;%path% && python main.py"

# Linux/Mac 系统
python main.py
```

---

## 🔧 配置说明

### CSV 配置文件：`github.csv`

```csv
tag,owner,repo,current_version,latest_version,last_checked
,microsoft,edit,v1.2.1,v1.2.1,1775188923
android,gkd-kit,gkd,v1.11.6,v1.11.6,1775188923
xposed,shatyuka,Zhiliao,v26.02.03,v26.02.03,1775188923
xposed,Dr-TSNG,ZygiskNext,v1.3.3,v1.3.3,1775188923
xposed,yujincheng08,BiliRoaming,,v1.7.0,1775188923
python,astral-sh,uv,,v0.11.3,1775188923
clash,Clash-Verge-rev,clash-verge-rev,,v2.4.7,1775188923
network,zhongyang219,TrafficMonitor,,V1.86,1775188923
```

### 字段说明

| 字段 | 必填 | 更新方式 | 说明 |
|------|------|----------|------|
| `tag` | ❌ | 手动 | 分类标签，非空时目录为 `releases/0{tag}/...` |
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
    "tag": "android",
    "owner": "gkd-kit",
    "repo": "gkd",
    "latest_version": "v1.11.6",
    "current_version": "v1.10.0",
    "has_update": true,
    "html_url": "https://github.com/gkd-kit/gkd/releases/tag/v1.11.6",
    "last_checked": 1774773371,
    "assets": [
      {
        "filename": "gkd-v1.11.6.apk",
        "download_url": "https://github.com/gkd-kit/gkd/releases/download/v1.11.6/gkd-v1.11.6.apk",
        "sha256": "abc123...",
        "size": "3.87 MB",
        "published_at": "2024-12-13T18:03:00Z"
      }
    ],
    "downloaded_assets": [
      {
        "filename": "gkd-v1.11.6.apk",
        "file_path": "/job/github/releases/0android/gkd-kit/gkd/v1.11.6/gkd-v1.11.6.apk",
        "sha256": "abc123...",
        "file_size": 4055000,
        "status": "downloaded"
      }
    ]
  }
]
```

---

## 🔄 执行流程

```
┌─────────────────────────────────────────────────────────────┐
│  1. 初始化                                                   │
│     ├─ 自动检测脚本所在目录（相对路径）                        │
│     └─ 创建 aiohttp 异步会话                                 │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  2. 读取 CSV                                                 │
│     └─ 解析字段: tag, owner, repo, current_version,          │
│                  latest_version, last_checked                │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  3. 遍历每个仓库（异步顺序执行）                               │
│     ├─ 请求间隔: 3 秒（避免 429）                             │
│     └─ Shields.io 异步获取最新版本号                          │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  4. 获取下载资产（异步）                                       │
│     ├─ Xget API: https://xget.xi-xu.me/gh/{owner}/{repo}/... │
│     ├─ 429 速率限制自动重试（最多 3 次）                       │
│     └─ 解析 HTML 提取资产信息                                 │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  5. 版本对比                                                 │
│     └─ has_update = (latest != current) && (latest != "")    │
└─────────────────────────────────────────────────────────────┘
                          ↓
┌─────────────────────────────────────────────────────────────┐
│  6. 下载资产文件（仅在有更新时，异步）                          │
│     ├─ 根据 tag 决定目录结构                                  │
│     │   ├─ 有 tag: releases/0{tag}/{owner}/{repo}/{version}/ │
│     │   └─ 无 tag: releases/{owner}/{repo}/{version}/        │
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
│     └─ 有更新的仓库列表 [tag] owner/repo: old → new          │
└─────────────────────────────────────────────────────────────┘
```

---

## 🛠️ 使用指南

### 1. 检查所有仓库版本

```bash
python check_releases.py
```

### 2. 查看检查结果

```bash
cat releases.json
```

### 3. 添加新仓库

编辑 `github.csv`，添加一行：

```csv
tag,owner,repo,current_version,latest_version,last_checked
newtag,newowner,newrepo,,, 
```

首次运行时 `current_version` 为空，不会触发下载。需要手动设置一个旧版本才会触发。

### 4. 更新本地版本

当你升级了某个软件后，手动更新 CSV 中的 `current_version`：

```csv
android,gkd-kit,gkd,v1.11.7,v1.11.7,1774773371
```

### 5. 设置定时任务

```bash
# 每 6 小时检查一次（推荐）
0 */6 * * * cd /path/to/github && python check_releases.py >> cron.log 2>&1
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

| 特点 | 说明 |
|------|------|
| ✅ 国内可访问 | 无需代理 |
| ✅ 完整资产信息 | 包含下载链接和校验码 |
| ⚠️ 有速率限制 | 需控制请求频率 |
| ⚠️ 版本格式差异 | 部分仓库需要不带 v 的版本号 |

**版本格式兼容**：脚本会自动尝试两种格式：
- `v1.11.6`（带 v）
- `1.11.6`（不带 v）

当第一种格式返回 404 时，自动尝试第二种格式。

### Ghproxy - 加速下载

```
GET https://ghproxy.net/{original_github_url}
```

---

## 🚨 错误处理

### 429 速率限制自动重试

| HTTP 状态码 | 处理方式 |
|-------------|----------|
| **429** | 速率限制，读取 Retry-After 或指数退避后重试（最多 3 次） |
| **404** | 资产不存在，自动尝试另一种版本格式（带 v / 不带 v） |
| **其他** | 记录错误日志，继续处理下一个仓库 |

**版本格式兼容逻辑：**
```
1. 尝试 v26.02.03（带 v）
   ├─ 200 → 返回资产
   ├─ 404 → 尝试下一版本格式
   └─ 429 → 重试
2. 尝试 26.02.03（不带 v）
   ├─ 200 → 返回资产
   └─ 404 → 无资产
```

重试策略（仅 429）：
- 请求间隔：每个仓库之间等待 3 秒
- Retry-After：优先使用服务器建议的等待时间
- 指数退避：5s → 10s → 20s
- 最大重试：3 次

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

## 📝 更新日志

### v26.4.3A (2026-04-03)

- ✨ 新增：**network 分类**，新增 zhongyang219/TrafficMonitor 仓库监控
- ✨ 新增：**TrafficMonitor V1.86 下载**，成功下载所有平台安装包
- 📦 下载资产：包含 x64/x86/arm64ec 及 Lite 版本共 6 个文件
- 🔄 更新：uv 版本从 v0.11.2 更新到 v0.11.3

### v26.4.1A (2026-04-01)

- ✨ 新增：**xposed 分类**，新增 yujincheng08/BiliRoaming 仓库监控
- ✨ 新增：**BiliRoaming v1.7.0 下载**，成功下载 BiliRoaming_1.7.0.apk
- 🔧 改进：**日志初始化重构**，将 logging 配置从 check_releases.py 移至 main.py
- 🔧 改进：**程序启动输出**，在程序开始时打印 unixtime 时间戳、SCRIPT_DIR、LOG_DIR、LOG_FILE 信息
- 📦 优化：日志系统统一在主入口初始化，check_releases.py 通过 `logging.getLogger(__name__)` 获取 logger

### v26.3.31C (2026-03-31)

- ✨ 新增：**clash 分类**，新增 Clash-Verge-rev/clash-verge-rev 仓库监控
- ✨ 新增：**clash-verge-rev v2.4.7 下载**，成功下载所有平台安装包
- 📦 下载资产：包含 Windows (x64/arm64)、macOS (x64/arm64)、Linux (deb/rpm) 多平台安装包

### v26.3.31B (2026-03-31)

- ✨ 新增：**python 分类**，新增 astral-sh/uv 仓库监控
- ✨ 新增：**uv v0.11.2 下载**，成功下载 uv 的所有平台文件（Windows/macOS/Linux 多架构支持）
- 📦 下载资产：包含 x86_64、aarch64、i686、armv7、powerpc64le、riscv64gc、s390x 等多平台安装包

### v26.3.31A (2026-03-31)

- ✨ 新增：**日志系统**，使用 logging 模块记录运行日志
- ✨ 新增：**日志自动清理**，自动清理超过 30 天的旧日志文件
- ✨ 新增：**数据库目录**，创建 db 目录用于存储数据库文件
- 🔧 改进：**临时文件目录**，从 `releases/tmp` 改为 `tmp`（符合项目规则）
- 🔧 改进：**主入口文件**，重构 main.py 作为正确的程序入口
- 🔧 改进：**版本号格式**，从 `1.5.0` 改为 `26.3.31A`（符合项目规则）
- 📦 依赖：新增 logging（标准库）

### v1.5.0 (2026-03-30)

- ✨ 新增：**异步网络请求**，使用 aiohttp 替代 urllib，提升效率
- ✨ 新增：**xposed 分类**，新增 Dr-TSNG/ZygiskNext 仓库
- 🔧 改进：**版本格式兼容优化**，404 时自动尝试另一种格式（带 v / 不带 v）
- 🔧 改进：移除 404 重试逻辑（资产不存在时尝试另一版本格式即可）
- 📦 依赖：新增 aiohttp（异步 HTTP 客户端）

### v1.4.0 (2026-03-30)

- ✨ 新增：**tag 分类功能**，支持按标签分类存储下载文件
- ✨ 新增：**版本格式兼容**，自动尝试带 v 和不带 v 的版本格式
- 🔧 改进：路径配置改为相对脚本目录，支持任意位置部署
- 🔧 改进：CSV 增加 `tag` 列（最左侧）

### v1.3.0 (2026-03-29)

- ✨ 新增：自动下载资产文件（通过 ghproxy 加速）
- ✨ 新增：SHA256 校验码验证，确保下载文件完整性
- ✨ 新增：已存在文件自动跳过（校验码匹配时）

### v1.2.0 (2026-03-29)

- ✨ 新增：通过 xget 获取下载资产
- ✨ 新增：429 速率限制自动处理

### v1.1.0 (2026-03-29)

- 改用 shields.io 查询版本（绕过中国大陆 GitHub API 限制）

### v1.0.0 (2026-03-29)

- 初始版本

---

*最后更新：2026-04-03*
*版本：26.4.3A*