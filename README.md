# HX-Git-DB

将 Git 仓库作为轻量级数据库, 支持 RAII 风格的文件读写与自动同步。

零依赖, 仅需系统安装 `git`。适用于 GitHub Actions 工作流中的数据持久化场景。

## 安装

```bash
# 从源码安装
pip install git+https://github.com/HengXin666/HX-Git-DB.git

# 或本地开发
git clone https://github.com/HengXin666/HX-Git-DB.git
cd HX-Git-DB
pip install -e .
```

## 快速开始

```python
from hx_git_db import make_database, MsgType

with make_database("https://github.com/user/repo.git", "data") as db:
    with db.open("config.json") as f:
        data = f.read_json()
        data["count"] = data.get("count", 0) + 1
        f.write_json(data)
    # 退出 with 时自动 commit + push + 清理临时目录
```

## 两种模式

### only 模式

分支永远只有一个提交, 每次 `push -f`, 不保留历史。适合存储不需要版本管理的数据(如缓存、状态快照)。

```python
db = make_database("https://github.com/user/repo.git", "data", only=True)
```

### 普通模式

标准 git 提交, 保留完整历史。push 冲突时自动 `pull --rebase` 重试(最多 3 次)。

```python
db = make_database("https://github.com/user/repo.git", "data")
db.pull()

db.set_commit_msg(MsgType.FEAT, "更新配置")

with db.open("config.json") as f:
    f.write_json({"version": "2.0"})

db.push()
db.cleanup()
```

## GitHub Actions

在 workflow 中设置 `GITHUB_TOKEN` 环境变量, 库会自动检测并注入认证信息:

```yaml
jobs:
  sync-data:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - run: pip install git+https://github.com/HengXin666/HX-Git-DB.git

      - run: python sync.py
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

```python
# sync.py
from hx_git_db import make_database

with make_database("https://github.com/user/data-repo.git", "data", only=True) as db:
    with db.open("result.json") as f:
        f.write_json({"status": "success"})
```

也可以手动传入 token:

```python
db = make_database(
    "https://github.com/user/repo.git", "main",
    token="ghp_xxxx",
    git_user="my-bot",
    git_email="bot@example.com",
)
```

### 内置演示工作流

本仓库提供了两个可直接运行的 GitHub Actions 工作流, 分别演示 only 模式和普通模式:

| 工作流 | 文件 | 目标分支 | 模式 | 行为 |
|--------|------|----------|------|------|
| Demo Only Mode | `.github/workflows/demo-only.yml` | `example-only` | only | 每次运行写入 `[时间戳] only mode sync`, 分支永远只有一个提交 |
| Demo Normal Mode | `.github/workflows/demo-normal.yml` | `examples-no-only` | 普通 | 每次运行追加 `[时间戳] normal mode sync`, 保留完整提交历史 |

在仓库的 **Actions** 页面手动触发 (`workflow_dispatch`) 即可运行:

1. 进入 Actions 页面
2. 选择 **Demo Only Mode** 或 **Demo Normal Mode**
3. 点击 **Run workflow**
4. 运行完成后, 切换到对应分支查看 `log.txt` 文件

多次运行后对比两个分支:
- `example-only` 分支: `log.txt` 始终只有最新一行, git log 只有一个提交
- `examples-no-only` 分支: `log.txt` 逐行累积, git log 保留每次提交记录

## API

### `make_database(repo_url, branch, *, only, work_dir, token, git_user, git_email)`

创建数据库实例。

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `repo_url` | `str` | 必填 | 仓库地址 (HTTPS / SSH) |
| `branch` | `str` | `"main"` | 分支名 |
| `only` | `bool` | `False` | only 模式 |
| `work_dir` | `str \| None` | `None` | 本地工作目录, `None` 使用临时目录 |
| `token` | `str \| None` | `None` | 认证 token, `None` 自动读取 `GITHUB_TOKEN` |
| `git_user` | `str` | `"HX-Git-DB"` | git 提交用户名 |
| `git_email` | `str` | `"hx-git-db@noreply"` | git 提交邮箱 |

### `DataBase`

| 方法 | 说明 |
|------|------|
| `pull()` | 拉取远程数据(首次自动 clone) |
| `push(commit_msg=None)` | 提交并推送变更 |
| `open(path) -> DataFile` | 打开数据文件 |
| `set_commit_msg(MsgType, msg)` | 设置提交消息, 如 `[feat] xxx` |
| `set_raw_commit_msg(msg)` | 设置原始提交消息 |
| `cleanup()` | 清理临时目录 |

### `DataFile`

| 方法 | 说明 |
|------|------|
| `read() -> str` | 读取文本 |
| `read_bytes() -> bytes` | 读取二进制 |
| `read_json() -> Any` | 读取 JSON |
| `write(content)` | 写入文本 |
| `write_bytes(content)` | 写入二进制 |
| `write_json(data)` | 写入 JSON |
| `delete()` | 删除文件 |

### `MsgType`

| 值 | 格式化结果 |
|----|-----------|
| `MsgType.FEAT` | `[feat] message` |
| `MsgType.FIX` | `[fix] message` |

## 可靠性

- **push 冲突自动重试**: 普通模式下 push 失败时, 自动 `pull --rebase` 后重试, 最多 3 次
- **rebase 冲突兜底**: rebase 出现冲突时, 自动 abort 并 reset 到远程最新状态, 重新提交
- **git 命令超时**: 所有 git 操作默认 120 秒超时, 防止网络问题导致永久阻塞
- **异常安全**: `with` 语句中发生异常时不会自动 push, 避免推送脏数据
- **日志追踪**: 通过 `logging.getLogger("hx-git-db")` 获取详细的操作日志

## License

MIT
