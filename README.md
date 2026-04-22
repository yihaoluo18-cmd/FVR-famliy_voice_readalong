# GPT-SoVITS v2Pro（GitHub 上传精简版 / test1）

本仓库用于保存**业务代码与脚本**，已剔除**大模型、运行时环境和静态大资源**，便于上传到 GitHub 进行版本管理与协作开发。

## 目录说明

- **`modules/`**：后端核心业务模块（训练、推理、接口、题库/涂色/伴宠等）
- **`微信小程序final/`**：微信小程序前端代码
- **`env/`**：环境安装脚本与示例配置（敏感配置仅保留 `.example`）
- **`tools/`**：项目工具脚本（含权重转换、维护脚本等）
- **`start_wx_api.sh`**：根目录唯一的“一键启动后端”脚本（推荐入口）

## 已排除内容（不在当前上传包中）

这些内容体积大或与本地环境强绑定，**不建议提交到 GitHub**：

- **`GPT_SoVITS/`**：大模型与训练框架目录
- **`venv/`**：本地虚拟环境
- **`assets/`**：静态大资源（题库/图片/素材等）
- **根目录大权重文件**：如 `*.pth` / `*.ckpt` 等
- **本地敏感配置**：如 `env/wx_api.env`、`*.env`、`*.env.local` 等

> 说明：本仓库通过 `.gitignore` 规避上述内容；部署时需要你从 Release/外部存储补齐。

## 安全注意（必须）

- **不要提交任何真实密钥**（API Key、Token、Secret、微信 AppID/Secret 等）。
- 请使用示例配置生成本地配置文件：

```bash
cp env/wx_api.env.example env/wx_api.env
```

然后在 `env/wx_api.env` 内填写你自己的密钥。该文件**仅本地使用**，已被 `.gitignore` 忽略。

## 本地运行（简版）

1. **安装依赖**：
   - Linux/macOS：运行 `env/setup_env.sh`
   - Windows：运行 `env/setup_env.cmd`
2. **填写环境变量**：按上文复制并编辑 `env/wx_api.env`
3. **启动后端**：

```bash
bash ./start_wx_api.sh
# 或仅启动主服务
bash ./start_wx_api.sh --wx-only
```

## 上传建议

- 推荐将本目录解压后直接：
  - `git init`
  - `git add .`
  - `git commit -m "init"`
  - `git push`
- 首次上传后，后续仅提交代码变更；**不要把模型、资源和本地环境再传上去**。

## GitHub Release 大资源清单（维护者）

后续你可将大资源放到 GitHub Release（或外部存储）供部署侧下载，例如：

- `GPT_SoVITS_part01.zip`
- `GPT_SoVITS_part02.zip`
- `GPT_SoVITS_part03.zip`
- `GPT_SoVITS_part04.zip`
- `assets_release.zip`
- `fvr_deploy_output.zip`（可选：推荐附带 `./output/` 默认数据快照）

