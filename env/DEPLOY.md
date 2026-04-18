# 后端部署说明（亲声伴读园 / GPT-SoVITS 集成）

本文档说明在**新 Linux 主机**上从零部署：不随包分发 `venv/`，用脚本与锁文件复现 Python 环境；权重与 `GPT_SoVITS` 代码需单独准备。**本机为 Windows 且使用 Git Bash** 执行脚本时，请先阅读「§1 前置条件」下的 **Windows：在 Git Bash 里跑本仓库脚本**。**微信小程序联调**（含「不校验合法域名」等）见 **第 8 节**。

---

## 0. Windows + Git Bash：本会话已验证的完整环境配置（逐步照做）

以下步骤对应在 **Windows 10/11** 上，用 **Git Bash** 在本仓库根目录完成 **Python 虚拟环境创建**、**依赖安装**、**可启动 `start_wx_api.sh`** 的全过程。若你的机器此前从未装过合适版本的 Python，请从 **0.1** 做到 **0.8**；若已有 Python 3.11 且 `py -3.11` 可用，可从 **0.3** 起。

### 0.1 安装 Git for Windows（含 Git Bash）

1. 安装 [Git for Windows](https://git-scm.com/download/win)，安装完成后开始菜单中应有 **Git Bash**。
2. 打开 **Git Bash**，后续 `.sh` 脚本均在此终端执行（不要用 PowerShell 直接执行 `.sh`，除非显式调用 `bash.exe script.sh`）。

### 0.2 本仓库在 Windows 上的典型问题（为何不能只用 `python3`）

| 现象 | 原因 |
|------|------|
| `setup_env.sh` 报「需要 Python 3.10+，当前为空」或版本异常 | Git Bash 里 `python3` 常指向 **Microsoft Store 占位符**，不是真实解释器。 |
| `python` 版本为 3.8.x | PATH 中 **Miniconda/Anaconda** 的 `python` 优先，不满足 ≥3.10。 |
| `py -3` 指向 3.13 | 可用，但部分依赖在 Windows 上 **无 wheel 需编译**（如 `pyopenjtalk`、`jieba_fast`），易失败。 |
| `venv/bin/pip` 找不到 | Windows 下 venv 使用 **`venv/Scripts/`**，脚本已做兼容。 |
| `ModuleNotFoundError: No module named 'modules'` | 仅把 `GPT_SoVITS/eres2net` 加入 `PYTHONPATH` 不够，需包含 **项目根目录**（已写入 `start_wx_api.sh`）。 |
| `UnicodeEncodeError`（✅、⚠️ 等） | 控制台默认 **GBK**，`print` 输出 emoji 可能失败（`wx_api.py` 已做 Windows 下 stdout 重配 + 环境变量）。 |
| 端口 9880 占用后脚本立刻退出 | 原脚本用 **`ss`**（Linux）查端口，Windows 上常不存在；已改为 **`netstat` + `taskkill`**，并修复 `grep` 无匹配时 **`set -e`/`pipefail` 误退出**。 |
| 绘本书名/图片乱码 | 解压 `.tar.gz` 时中文路径编码错误；魔法书架已支持以 **`modules/books_library/book_new`** 为主库动态索引。 |

### 0.3 安装 Python 3.11（强烈推荐，wheel 覆盖好于 3.13）

在 **PowerShell（管理员）** 或普通 PowerShell 中执行（若 `winget` 报证书/源错误，加 `--source winget`）：

```powershell
winget install Python.Python.3.11 -e --accept-source-agreements --accept-package-agreements --source winget
```

验证：

```powershell
py -0p
py -3.11 --version
```

应能看到 `Python 3.11.x` 与安装路径。

### 0.4 进入项目根目录（Git Bash）

路径请按你的实际目录修改（示例为桌面项目）：

```bash
cd "/c/Users/你的用户名/Desktop/项目测试2"
```

若 `./setup_env.sh` 无执行权限：

```bash
chmod +x setup_env.sh start_wx_api.sh modules/tts_backend/scripts/start_api_v2.sh
```

### 0.5 创建虚拟环境并安装依赖（两种方式任选其一）

**方式 0：Windows 解压后「一键」建环境（推荐不熟悉 Git Bash 时）**

在项目根目录**双击** `setup_env.cmd`，或在 **cmd** 中执行：

```bat
cd /d C:\你的路径\项目测试2
setup_env.cmd
```

- 会优先用 **`py -3.11 -m venv venv`**，失败则回退 **`py -3`**；再按是否存在 **`requirements-lock.txt`** 决定安装锁文件或 **`requirements.txt`**。  
- 强制删除旧环境重建：`setup_env.cmd --recreate`  
- 与 `setup_env.sh` 中 **`CUDA_PIP=1`** 等价的 GPU 预装：先执行 `set CUDA_PIP=1` 再运行 `setup_env.cmd`（**仅在你确认 Windows 上需要且 wheel 可用时**）。

完成后仍需在 **Git Bash** 里启动服务：`./start_wx_api.sh`（见 **0.7**）。

**方式 A：直接用 `py -3.11`（与下文手工步骤一致）**

```bash
py -3.11 -m venv venv
./venv/Scripts/python.exe -m pip install -U pip wheel "setuptools<82"
./venv/Scripts/pip.exe install -r requirements.txt
```

说明：`requirements.txt` 在本仓库中用于在**缺少** `requirements-lock.txt` 时安装依赖；其中对 **Windows** 跳过了需本机编译的 **`pyopenjtalk`**、**`jieba_fast`**（中文分词回退到 **`jieba`**，见 `GPT_SoVITS/text/chinese.py` 的 try/except）。**Python 3.13** 与 `numpy<2` 冲突处已用环境标记分支；**优先使用 3.11** 可减少编译问题。

**方式 B：使用仓库脚本 `./setup_env.sh`（推荐与文档统一）**

脚本会：自动选择 `python3.10`…`python3`、`python`、再尝试 **`py -3.11` → `py -3.12` → …**；在 Windows 上使用 **`venv/Scripts/pip`**；无 `requirements-lock.txt` 时回退到 **`requirements.txt`**；并执行 `pip install -U pip wheel "setuptools<82"` 与 `pip install -r <锁文件或 requirements.txt>`。

```bash
./setup_env.sh --recreate
```

若从未建过环境，也可不加 `--recreate`：

```bash
./setup_env.sh
```

### 0.6 启动前环境变量（已由 `start_wx_api.sh` 设置，此处仅作说明）

`start_wx_api.sh` 会导出（默认值如下，可自行覆盖）：

```bash
export PYTHONPATH="$PROJECT_ROOT:$PROJECT_ROOT/GPT_SoVITS/eres2net:${PYTHONPATH:-}"
export PYTHONUTF8="${PYTHONUTF8:-1}"
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
```

### 0.7 启动服务

```bash
./start_wx_api.sh
```

或仅主服务：

```bash
./start_wx_api.sh --wx-only
```

自检示例（在 **Git Bash** 或已安装 `curl.exe` 的环境）：

```bash
curl.exe -sS -m 3 http://127.0.0.1:9880/coloring/health
curl.exe -sS -m 3 http://127.0.0.1:9881/readalong/health
```

### 0.8 源码分发包说明（不含超大目录、压缩包与本机虚拟环境）

若需将「除 **GPT_SoVITS**、根目录两个超大 **`.tar.gz`**、以及本机 **`venv/` / `.venv/`** 以外的源码」打成一份 zip，可在项目根目录执行（PowerShell）：

```powershell
# 若尚未创建 venv，可用系统 Python：python tools\pack_source_zip.py
.\venv\Scripts\python.exe tools\pack_source_zip.py
```

生成文件默认位于**上一级目录**（与项目文件夹同级），文件名形如：`项目测试2-src-no-gptsovits-no-big-tarballs.zip`。  
**不包含**：`GPT_SoVITS/`；`frontend_trim10img_extracted/`（大体积解压副本，脚本默认永不打入 zip）；`venv/`、`.venv/`（**不打包已 pip 安装的环境**，避免体积巨大且不可移植）；根目录 `excluded_big_assets_bundle_20260402-154902.tar.gz`、`frontend_trim10img_10speaker_5books_repack_20260402-155430.tar.gz`。  
解压后需自行准备 **`GPT_SoVITS`** 与模型权重，再在目标机器执行 **0.5～0.7** 重建 `venv`。

---

## 1. 前置条件

| 项 | 说明 |
|----|------|
| 系统 | Linux x86_64（与当前开发机一致时依赖最稳） |
| Python | **3.10+**（推荐 `python3.10`） |
| GPU（可选） | NVIDIA 驱动 + CUDA；TTS 推理用 GPU 时需能装 **PyTorch CUDA 12.4** 官方 wheel |
| 磁盘 | 除代码外，预留 **GPT 权重 + SoVITS 权重 + GPT_SoVITS 目录** 所需空间（通常数 GB 级） |

### Windows：在 Git Bash 里跑本仓库脚本

若你**本机是 Windows**，用 **Git Bash**（随 Git for Windows 安装）执行 `.sh` 时，注意与 Linux 服务器的差异：

| 项 | 说明 |
|----|------|
| 适用场景 | 本地解压、跑 `setup_env.sh`、简单试跑 `start_wx_api.sh`；**与线上一致的生产部署仍建议用 Linux 或 WSL2**，避免 PyTorch/CUDA 与路径差异。 |
| 路径 | 仓库放在**无空格、无中文**目录，例如 `C:\dev\story-app`。在 Git Bash 里对应 **`/c/dev/story-app`**，`cd` 到该目录再执行脚本。 |
| Python | 在 Windows 安装 **Python 3.10+**，安装时勾选 **Add python.exe to PATH**。在 Git Bash 中执行 `python --version`；若无 `python3`，脚本里的 `python3` 可能不可用，可装官方 Python 或改用 **WSL2** 内的 `python3.10`。 |
| 执行方式 | 若 `./setup_env.sh` 提示无权限，用显式 bash：**`bash setup_env.sh`**；带 GPU 预装：**`CUDA_PIP=1 bash setup_env.sh`**（仅当该预装步骤在 Windows 上可用时，见下行）。 |
| 换行符 CRLF | 若报错含 **`$'\r'`** 或 **`bad interpreter`**，说明 `.sh` 被保存成 Windows 换行。处理：安装 `dos2unix` 后执行 `dos2unix setup_env.sh start_wx_api.sh`，或设置 **`git config core.autocrlf false`** 后重新克隆/检出，再保证编辑器以 **LF** 保存 shell 脚本。 |
| CUDA / PyTorch | `setup_env.sh` 里 **`CUDA_PIP=1` 面向 Linux 的 cu124 官方 wheel**；在**原生 Windows**上装 GPU 版 PyTorch 请打开 [pytorch.org](https://pytorch.org) 选择 **Windows + CUDA**，手动安装与 `requirements-lock.txt` 中版本兼容的 `torch` / `torchaudio` 后，再 **`pip install -r requirements-lock.txt`**。更省事的做法是在 **WSL2（Ubuntu）** 或 **Linux** 上使用文档第 3 节的 `CUDA_PIP=1`。 |
| 更省心的选择 | **WSL2（Ubuntu）**：在 WSL 终端里把项目放在 Linux 文件系统（如 `~/proj`），再按「第 3 节」Linux 流程操作，与服务器最接近。 |

```bash
# Git Bash 示例：进入仓库根目录（按你的实际路径修改）
cd /c/dev/story-app

# 建环境（Windows 上多数情况先不传 CUDA_PIP，或改用 WSL2 执行带 CUDA 的安装）
bash setup_env.sh

# 需要重建虚拟环境时
# bash setup_env.sh --recreate

# 启动（同样在仓库根目录）
# bash start_wx_api.sh
```

---

## 2. 获取代码与资源

1. 解压或克隆项目到目标目录，例如 `/opt/story-app`（**路径勿含中文/空格**，避免脚本与部分库异常）。
2. **不要**复制开发机的 `venv/`；需携带 **`requirements-lock.txt`** 与 **`setup_env.sh`**。
3. 单独准备（若打包拆分）：
   - 目录 **`GPT_SoVITS/`**（推理依赖的代码与资源）
   - **`GPT_weights_v2Pro/`**、**`SoVITS_weights_v2Pro/`**（默认文件名需与后端配置一致，见第 4 节）

---

## 3. 创建虚拟环境并安装依赖

在项目根目录执行（**有 NVIDIA GPU 且要用 CUDA** 时用第一行环境变量）：

```bash
# GPU：先预装 CUDA 版 PyTorch，再安装全量锁文件（与 setup_env.sh 内逻辑一致）
CUDA_PIP=1 ./setup_env.sh

# 仅 CPU 或无对应 CUDA：不传 CUDA_PIP
# ./setup_env.sh

# 若曾装坏环境，可强制删 venv 重建
# ./setup_env.sh --recreate
```

脚本等价于：用 `python3.10`（或 `python3`）创建 `./venv`，再 `pip install -r requirements-lock.txt`。  
**更新依赖**：在开发机更新 venv 后重新执行 `pip freeze > requirements-lock.txt`，再分发新锁文件。

---

## 4. 权重与代码路径（必查）

后端默认在**项目根目录**下查找（与 `modules/tts_backend/wx_api.py` 中逻辑一致）：

- `GPT_weights_v2Pro/` — 例如含 `30s-e15.ckpt` 等  
- `SoVITS_weights_v2Pro/` — 例如含 `30s_e8_s184.pth` 等  
- `GPT_SoVITS/` — 推理与子模块依赖  

若路径或文件名不同，需在代码/配置中改为你的实际路径（生产环境勿保留 Windows 绝对路径）。

---

## 5. 环境变量 `wx_api.env`

```bash
# 从示例复制，再编辑真实密钥（勿提交 git）
cp wx_api.env.example wx_api.env
# vim wx_api.env   # 至少配置 AI_API_KEY、AI_BASE_URL、各 AI_MODEL_* 等
```

`./start_wx_api.sh` 会**优先** `source` 根目录的 `wx_api.env`；不存在时才回退加载 `wx_api.env.example`。

---

## 6. 启动服务

```bash
cd /opt/story-app   # 换成你的项目根目录

# 默认：跟读 9881 后台 + 主服务 9880 前台
./start_wx_api.sh

# 仅主服务
# ./start_wx_api.sh --wx-only

# 健康检查（不常驻进程时可单独看脚本输出）
# ./start_wx_api.sh --docs
```

常用环境变量（可选）：

```bash
# 指定本机对外监听（默认主服务已是 0.0.0.0）
export WX_HOST=0.0.0.0
export WX_PORT=9880

# 固定使用某张 GPU（默认 auto 会挑显存较空闲的卡）
export WX_API_CUDA_VISIBLE_DEVICES=0

./start_wx_api.sh
```

日志默认在 **`train/runtime/`** 下，详见脚本内 `LOG_WX`、`LOG_READALONG`。

---

## 7. 端口与自检

| 服务 | 默认端口 | 说明 |
|------|----------|------|
| 主 API（含静态、业务） | **9880** | 小程序/前端配置的 base URL 应对准此端口 |
| 跟读评测 | **9881** | 与主服务联调 |

```bash
# 本机探测（与 start_wx_api.sh --docs 行为类似）
curl -sS http://127.0.0.1:9880/ | head
curl -sS http://127.0.0.1:9881/readalong/health
```

---

## 8. 微信小程序前端（正常使用）

### 8.1 用微信开发者工具打开工程

- 目录：**`微信小程序final`**（与仓库根目录同级；勿选错到仓库根目录）。
- 打开 [微信开发者工具](https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html) → **导入** → 选择上述文件夹 → 填写/使用测试号或真实 AppID（`project.config.json` 内已有 `appid`，需有权限的账号才能预览）。

### 8.2 开发/联调必开：不校验合法域名

联调 **HTTP**、**局域网 IP**、**自签名 HTTPS** 或未在公众平台配置的域名时，必须在开发者工具里关闭域名校验，否则请求会被拦截。

1. 微信开发者工具右上角 **「详情」**。
2. 切到 **「本地设置」**（部分版本在 **「项目设置」→「本地设置」**）。
3. 勾选 **「不校验合法域名、web-view（业务域名）、TLS 版本以及 HTTPS 证书」**。

```text
# 勾选后，开发版/预览版才可访问例如：
#   http://127.0.0.1:9880
#   http://192.168.1.10:9880
# 未勾选时常见现象：request:fail url not in domain list / 不在以下 request 合法域名列表中
```

**注意：** 该选项**仅作用于开发者工具与本机预览流程**。**正式上架**的小程序必须在 [微信公众平台](https://mp.weixin.qq.com/) → **开发管理** → **开发设置** → **服务器域名** 中配置 **request 合法域名**（需 **HTTPS**、已备案域名等），不能再依赖「不校验」开关。

### 8.3 后端 API 地址怎么填

全局默认写在 **`微信小程序final/app.js`** 顶部常量 **`DEFAULT_API_BASE_URL`**（一般为 `http://127.0.0.1:9880`）。

| 场景 | 建议地址 |
|------|----------|
| 开发者工具**模拟器** + 后端在本机同一台电脑 | `http://127.0.0.1:9880` |
| **真机预览 / 真机调试**（手机与电脑同一局域网） | `http://<电脑的局域网 IP>:9880`，**不要用 127.0.0.1**（127.0.0.1 指向手机自身，会连不上电脑） |
| 公网或内网穿透 | `https://你的域名` 或 `http://公网IP:9880`（仅开发可配合 8.2；上线需 HTTPS + 配置合法域名） |

持久化方式（任选其一即可与代码逻辑一致）：

- 在小程序内若页面支持修改 API 根地址，保存后会写入本地存储键 **`apiBaseUrl`**。
- 或在开发者工具 **调试器 → Storage** 手动新增/修改 **`apiBaseUrl`** 为上述 URL（勿带末尾 `/`）。
- 代码中通过 **`getApp().setApiBaseUrl(url)`** / **`getApp().getApiBaseUrl()`** 读写（见 `app.js`）。

后端需监听 **`0.0.0.0`**（默认 `start_wx_api.sh` 中主服务已是 `0.0.0.0`），防火墙放行 **9880**（跟读相关还需 **9881**）。

### 8.4 双端口（9880 + 9881）

跟读、演说等能力会访问主服务 **9880**，部分逻辑会再请求 **9881**（与 `readalong` 等一致）。联调时请用 **`./start_wx_api.sh`** 同时拉起两路服务，避免只开 9880 导致部分接口失败。

### 8.5 依赖构建（若改过 `package.json`）

工程启用了 **「使用 npm 模块」**（见 `project.config.json`）。若你新增或更新了 npm 依赖，在开发者工具菜单 **「工具」→「构建 npm」**，生成/更新 **`miniprogram_npm`** 后再编译。

### 8.6 静态资源与图片

图片等若请求后端 **`/static/miniprogram_assets/...`**，需部署侧已包含 **`wx_static/miniprogram_assets`**（或你们 `asset-url` 所映射的目录），否则会出现裂图；联调时同样受 **8.2 合法域名** 规则约束。

---

## 9. 常见问题

1. **`pip install` 失败或 torch 版本不对**  
   - 确认 Python ≥3.10；GPU 场景使用 `CUDA_PIP=1 ./setup_env.sh`。  
   - 非 Linux 或特殊架构需自行按 [PyTorch 官网](https://pytorch.org) 选择 wheel，再装其余依赖。

2. **`invalid device ordinal` / CUDA 报错**  
   - 检查 `nvidia-smi`；用 `WX_API_CUDA_VISIBLE_DEVICES` 指定存在的卡号。

3. **大文件 tar 包损坏**  
   - 分发后务必执行 `tar -tzf xxx.tar.gz` 或 `gzip -t xxx.tar.gz` 校验；异常 EOF 需重新打包传输。

4. **不打包 venv**  
   - 交付物包含：项目代码 + `requirements-lock.txt` + `setup_env.sh`；对方执行第 3 节即可。

5. **小程序提示「不在合法域名列表」或 request 失败**  
   - 开发阶段：按 **第 8.2 节** 勾选 **不校验合法域名** 等项。  
   - 真机：确认 **`apiBaseUrl`** 为电脑局域网 IP，且手机与电脑同网；关闭手机「仅 WLAN 下使用」等限制若影响访问。  
   - 正式版：必须在公众平台配置 **HTTPS** 合法域名，不能长期依赖关闭校验。

---

## 10. 最小验收清单

**后端**

- [ ] `./setup_env.sh`（或 `CUDA_PIP=1 ./setup_env.sh`）无报错结束  
- [ ] `GPT_weights_v2Pro`、`SoVITS_weights_v2Pro`、`GPT_SoVITS` 路径与文件存在  
- [ ] `wx_api.env` 已配置且非空密钥项已填写  
- [ ] `./start_wx_api.sh` 启动后，`9880` / `9881` 健康检查通过  

**小程序前端**

- [ ] 微信开发者工具打开 **`微信小程序final`**，**详情 → 本地设置** 已勾选 **不校验合法域名、web-view（业务域名）、TLS 版本以及 HTTPS 证书**（联调 HTTP / 局域网时必做）  
- [ ] `apiBaseUrl` 与场景一致：模拟器可用 `127.0.0.1:9880`；**真机**为 `http://<电脑局域网IP>:9880`  
- [ ] 需要跟读/演说等能力时，确认 **9880 + 9881** 均已启动  

完成以上即可认为联调环境就绪；正式上线需按第 8.2 节配置 HTTPS 与公众平台服务器域名。
