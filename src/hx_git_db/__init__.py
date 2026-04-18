"""HX-Git-DB: 将 Git 仓库作为轻量级数据库

用法:
    from hx_git_db import make_database, MsgType

    with make_database("https://github.com/user/repo.git", "data") as db:
        with db.open("config.json") as f:
            data = f.read_json()
            data["count"] = data.get("count", 0) + 1
            f.write_json(data)
"""

from .commit_msg import DEFAULT_COMMIT_MSG, MsgType
from .data_file import DataFile
from .database import DataBase


def make_database(
    repo_url: str,
    branch: str = "main",
    *,
    only: bool = False,
    work_dir: str | None = None,
    token: str | None = None,
    git_user: str = "HX-Git-DB",
    git_email: str = "hx-git-db@noreply",
) -> DataBase:
    """创建数据库实例

    Args:
        repo_url: 仓库地址 (支持任何 Git 仓库, 不限于 GitHub)
        branch: 分支名, 默认 "main"
        only: 是否为 only 模式.
              为 True 时每次 push -f, 分支永远只有一个提交, 不保留历史.
              为 False 时正常 git 提交, 保留完整历史.
        work_dir: 本地工作目录, 为 None 则使用临时目录
        token: 认证 token, 为 None 时自动从环境变量 GITHUB_TOKEN / GH_TOKEN 读取
        git_user: git 提交用户名, 默认 "HX-Git-DB"
        git_email: git 提交邮箱, 默认 "hx-git-db@noreply"

    Returns:
        DataBase 实例, 支持上下文管理器
    """
    return DataBase(
        repo_url,
        branch,
        only=only,
        work_dir=work_dir,
        token=token,
        git_user=git_user,
        git_email=git_email,
    )


__all__ = [
    "make_database",
    "DataBase",
    "DataFile",
    "MsgType",
    "DEFAULT_COMMIT_MSG",
]
