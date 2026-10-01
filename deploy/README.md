# GitHub main → 云端后端部署

GitHub 的 `main` 是唯一发布分支。新电脑克隆仓库即可开发；服务器从
GitHub 拉取代码，不再从个人电脑接收打包文件。Android APK 和独立的
`01tts-web` 前端仍使用各自发布流程，本脚本只更新 Python API。

## 本次核对（2026-10-01）

- GitHub：`main` 为 `8bbaf48`；`docs/add-claude-md` 为 `f2c1863`，只新增
  `CLAUDE.md`，已有待合并的 PR #1。合并其文档后可以删除这个已合并分支。
- 本地：当前在文档分支，分页和课程去重/生成优化尚未提交到 GitHub。
  `BLOG_LISTENING_LAB_OPTIMIZED.md` 是已有未跟踪文件，不纳入后端发布。
- 云端：`/opt/01tts/01tts-worker` 没有 Git 元数据，属于直接上传的文件。
  `api.py`、`worker.py`、依赖清单以及 15 个 `src/*.py` 中的 13 个与本地一致。
  云端 `config.py` 的 Moonshot 配置和 `deepseek_service.py` 的 Kimi 参数
  不再保留：生成器只调用 DeepSeek，Git 发布后云端的 Kimi 改动随旧目录一起退役。
- 云端旧测试和缺失的 `contracts/` 导致 6 项旧失败；完整仓库包含合同样例和
  新版测试。切换时必须使用完整仓库跑测试，不能继续仅覆盖几个源码文件。

本次准备阶段：本地和云端隔离目录均通过 113 项后端单元测试。
部署失败恢复、首次迁移恢复和手动回滚已通过模拟测试；正式生产切换
尚未执行。隔离验证目录为 `/opt/01tts/backups/git-deploy-check-20261001`。

## 日常开发与发布

新电脑第一次：

```bash
git clone https://github.com/zhchoice123/01tts.git
cd 01tts
git switch main
```

每次开始修改前先同步，完成修改后提交明确的文件：

```bash
git pull --ff-only origin main
# 修改代码并运行相关测试
git add <本次修改的文件>
git commit -m "fix(api): describe the change"
git push origin main
```

本地有未提交修改时先处理这些修改，再执行拉取；不要使用强推、reset 或
自动覆盖。多人协作时可使用短期分支和 PR，合并后删除；长期只维护 `main`。

下面的一次性初始化和发布命令必须在本部署脚本已合并到 GitHub `main` 后执行。
服务器从公开仓库只读拉取，无须把个人 GitHub token 放到云端。

服务器一次性初始化（现有服务器以 root 通过 SSH 登录）：

```bash
ssh tecent-server
git clone --branch main --single-branch https://github.com/zhchoice123/01tts.git /opt/01tts/repository
/opt/01tts/venv/bin/python /opt/01tts/repository/deploy/deploy_backend.py check
/opt/01tts/venv/bin/python /opt/01tts/repository/deploy/deploy_backend.py deploy
```

以后从任意能 SSH 到服务器的电脑发布：

```bash
ssh tecent-server '/opt/01tts/venv/bin/python /opt/01tts/repository/deploy/deploy_backend.py deploy'
curl -fsS https://api.zhchoice.xyz/health
```

服务正常时不需要每次重复 clone。部署脚本自己执行 `fetch` 和
`merge --ff-only origin/main`。相同提交通过测试后不会重复重启。

## 发布检查和回滚

`check` 拉取并准备代码、安装依赖、执行全部后端单元测试，不重启服务。
`deploy` 在相同检查通过后更新 systemd 的独立 drop-in 并重启；它保持原有
服务用户、环境文件、监听地址、端口和后台队列。部署锁防止同时发布。
服务器仓库有本地改动或无法快进时直接停止，留给人工处理。

每个 Git 提交有独立的代码和虚拟环境：

| 目录/文件 | 用途 |
| --- | --- |
| `/opt/01tts/repository` | `main` 拉取入口 |
| `/opt/01tts/releases/<commit>` | 固定提交的代码，包含共享合同样例 |
| `/opt/01tts/release-venvs/<commit>` | 此版本的 Python 依赖 |
| `/opt/01tts/settings/config.yaml` | 初次复制现有配置，课程代码只引用它 |
| `/etc/01tts-python-api.env` | 原有密钥、数据库、Redis、绝对音频路径 |
| `/opt/01tts/storage-python` | 原有音频和持久化文件 |
| `/opt/01tts/deployment-state.json` | 当前提交和上一次 systemd 配置 |

健康检查不通过时自动恢复原来的 systemd 配置并重启。也可以手动回滚：

```bash
ssh tecent-server '/opt/01tts/venv/bin/python /opt/01tts/repository/deploy/deploy_backend.py rollback'
```

首次回滚会恢复当前的上传式部署目录；后续回滚恢复上一个 Git 版本及其
依赖。脚本不会删除历史版本。检查状态和错误：

```bash
ssh tecent-server 'cat /opt/01tts/deployment-state.json'
ssh tecent-server 'systemctl status 01tts-python-api.service --no-pager'
ssh tecent-server 'journalctl -u 01tts-python-api.service -n 80 --no-pager'
```

发布会有一次短暂重启。代码回滚不会回滚数据库；涉及破坏性数据库迁移时
需要另行设计迁移和恢复步骤。本次归档表是新增表。当前依赖清单仍使用
版本下限；每版隔离环境保证回滚不会复用新版依赖，完全可重建的依赖锁定
可作为后续改进。自动部署到生产暂不启用，GitHub Actions 先负责测试和安全扫描。
