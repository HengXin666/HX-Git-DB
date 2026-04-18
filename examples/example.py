"""HX-Git-DB 使用示例"""

from hx_git_db import make_database, MsgType


def example_only_mode():
    """only 模式: 分支永远只有一个提交"""
    with make_database("https://github.com/user/private-data.git", "data", only=True) as db:
        with db.open("stats.json") as f:
            data = f.read_json()
            data["last_sync"] = "2026-04-18"
            data["count"] = data.get("count", 0) + 1
            f.write_json(data)

        with db.open("notes.txt") as f:
            f.write("这是一条笔记\n")


def example_normal_mode():
    """普通模式: 保留完整 git 历史"""
    db = make_database("git@github.com:user/config-repo.git", "config")
    db.pull()

    db.set_commit_msg(MsgType.FEAT, "更新配置文件")

    with db.open("app/config.json") as f:
        config = f.read_json()
        config["version"] = "2.0.0"
        f.write_json(config)

    db.push()
    db.cleanup()


def example_github_actions():
    """GitHub Actions 工作流中使用

    在 workflow yaml 中设置:
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

    库会自动检测 GITHUB_TOKEN 并注入到仓库地址中.
    """
    db = make_database(
        "https://github.com/user/data-repo.git",
        "data",
        only=True,
    )
    db.pull()

    with db.open("workflow_result.json") as f:
        f.write_json({"status": "success", "run": 42})

    db.push()
    db.cleanup()


def example_custom_token():
    """手动传入 token"""
    db = make_database(
        "https://github.com/user/repo.git",
        "main",
        token="ghp_xxxxxxxxxxxx",
        git_user="my-bot",
        git_email="bot@example.com",
    )
    db.pull()

    with db.open("data.json") as f:
        f.write_json({"key": "value"})

    db.set_commit_msg(MsgType.FIX, "修复数据格式")
    db.push()
    db.cleanup()


if __name__ == "__main__":
    print("请根据实际仓库地址修改示例代码后运行")
    print()
    print("API 概览:")
    print("  make_database(url, branch, only=True/False, token=...)")
    print("  db.open(path) -> DataFile (支持 with 语句)")
    print("  db.push() / db.pull()")
    print("  db.set_commit_msg(MsgType.FEAT, '消息')")
    print()
    print("GitHub Actions 中只需设置 GITHUB_TOKEN 环境变量即可自动认证")
