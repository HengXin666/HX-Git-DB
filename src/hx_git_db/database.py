"""核心数据库类, 将 Git 仓库作为轻量级数据存储"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import time
from urllib.parse import urlparse

from .commit_msg import DEFAULT_COMMIT_MSG, MsgType
from .data_file import DataFile

logger = logging.getLogger("hx-git-db")

GIT_TIMEOUT = 120
MAX_PUSH_RETRIES = 3
RETRY_DELAY = 2.0


def _run_git(
    args: list[str],
    cwd: str,
    *,
    timeout: int = GIT_TIMEOUT,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """执行 git 命令

    Args:
        args: git 子命令及参数
        cwd: 工作目录
        timeout: 超时秒数
        check: 是否在失败时抛出异常

    Returns:
        命令执行结果

    Raises:
        RuntimeError: git 命令执行失败 (仅 check=True)
        TimeoutError: git 命令超时
    """
    cmd_str = f"git {' '.join(args)}"
    logger.debug("执行: %s (cwd=%s)", cmd_str, cwd)

    try:
        result = subprocess.run(
            ["git", *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise TimeoutError(f"{cmd_str} 超时 ({timeout}s)") from e

    if check and result.returncode != 0:
        raise RuntimeError(
            f"{cmd_str} 失败 (code={result.returncode}):\n{result.stderr.strip()}"
        )

    logger.debug("返回: code=%d", result.returncode)
    return result


def _is_github_actions() -> bool:
    """检测是否在 GitHub Actions 环境中运行"""
    return os.environ.get("GITHUB_ACTIONS") == "true"


def _build_auth_url(repo_url: str, token: str) -> str:
    """将 token 注入 HTTPS 仓库地址

    Args:
        repo_url: 原始仓库地址
        token: 认证 token

    Returns:
        带认证信息的仓库地址
    """
    parsed = urlparse(repo_url)
    if parsed.scheme not in ("http", "https"):
        return repo_url
    return f"{parsed.scheme}://x-access-token:{token}@{parsed.hostname}{parsed.path}"


class DataBase:
    """Git 仓库数据库

    将一个 Git 仓库的指定分支作为轻量级数据存储.
    支持两种模式:
    - only 模式: 每次 push -f, 分支永远只有一个提交, 不保留历史
    - 普通模式: 正常 git 提交, 保留完整历史

    GitHub Actions 适配:
    - 自动检测 GITHUB_ACTIONS 环境
    - 自动使用 GITHUB_TOKEN 认证
    - 自动配置 git user.name / user.email

    用法:
        db = make_database("https://github.com/user/repo.git", "data")
        db.pull()
        with db.open("config.json") as f:
            data = f.read_json()
            data["count"] = data.get("count", 0) + 1
            f.write_json(data)
        db.push()
    """

    def __init__(
        self,
        repo_url: str,
        branch: str = "main",
        *,
        only: bool = False,
        work_dir: str | None = None,
        token: str | None = None,
        git_user: str = "HX-Git-DB",
        git_email: str = "hx-git-db@noreply",
    ) -> None:
        """
        Args:
            repo_url: 仓库地址 (支持 HTTPS / SSH)
            branch: 分支名
            only: 是否为 only 模式 (push -f, 永远只有一个提交)
            work_dir: 本地工作目录, 为 None 则使用临时目录
            token: 认证 token, 为 None 时自动从环境变量 GITHUB_TOKEN 读取
            git_user: git 提交用户名
            git_email: git 提交邮箱
        """
        self._branch = branch
        self._only = only
        self._commit_msg = DEFAULT_COMMIT_MSG
        self._changed_files: list[str] = []
        self._cloned = False
        self._git_user = git_user
        self._git_email = git_email

        token = token or os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if token and repo_url.startswith("http"):
            self._repo_url = _build_auth_url(repo_url, token)
        else:
            self._repo_url = repo_url
        self._display_url = repo_url

        if work_dir:
            self._work_dir = os.path.abspath(work_dir)
            self._is_temp = False
        else:
            self._work_dir = tempfile.mkdtemp(prefix="hx-git-db-")
            self._is_temp = True

        self._repo_dir = os.path.join(self._work_dir, "repo")

    @property
    def repo_url(self) -> str:
        """仓库地址 (不含 token)"""
        return self._display_url

    @property
    def branch(self) -> str:
        return self._branch

    @property
    def only(self) -> bool:
        return self._only

    @only.setter
    def only(self, value: bool) -> None:
        self._only = value

    @property
    def repo_dir(self) -> str:
        """本地仓库目录路径"""
        return self._repo_dir

    def set_commit_msg(self, msg_type: MsgType, message: str) -> None:
        """设置下次提交的消息

        Args:
            msg_type: 消息类型 (MsgType.FEAT / MsgType.FIX)
            message: 消息内容
        """
        self._commit_msg = msg_type.format(message)

    def set_raw_commit_msg(self, message: str) -> None:
        """设置下次提交的原始消息 (不经过格式化)

        Args:
            message: 完整的提交消息
        """
        self._commit_msg = message

    def _configure_git(self) -> None:
        """配置 git user 信息"""
        _run_git(["config", "user.name", self._git_user], cwd=self._repo_dir)
        _run_git(["config", "user.email", self._git_email], cwd=self._repo_dir)

    def pull(self) -> None:
        """从远程拉取数据

        首次调用时 clone 仓库, 之后调用时 pull 更新.
        如果远程分支不存在, 会创建一个新的孤立分支.
        """
        if not self._cloned:
            self._clone()
        else:
            self._pull()

    def _clone(self) -> None:
        """克隆仓库"""
        if os.path.exists(self._repo_dir):
            shutil.rmtree(self._repo_dir)

        result = _run_git(
            ["clone", "--single-branch", "--branch", self._branch,
             "--depth", "1", self._repo_url, "repo"],
            cwd=self._work_dir,
            check=False,
        )

        if result.returncode != 0:
            logger.info("分支 '%s' 不存在, 创建孤立分支", self._branch)
            os.makedirs(self._repo_dir, exist_ok=True)
            _run_git(["init"], cwd=self._repo_dir)
            _run_git(["remote", "add", "origin", self._repo_url], cwd=self._repo_dir)
            _run_git(["checkout", "--orphan", self._branch], cwd=self._repo_dir)

        self._configure_git()
        self._cloned = True

    def _pull(self) -> None:
        """拉取更新"""
        if self._only:
            result = _run_git(
                ["fetch", "origin", self._branch, "--depth", "1"],
                cwd=self._repo_dir,
                check=False,
            )
            if result.returncode == 0:
                _run_git(["reset", "--hard", f"origin/{self._branch}"], cwd=self._repo_dir)
        else:
            _run_git(
                ["pull", "--rebase", "origin", self._branch],
                cwd=self._repo_dir,
                check=False,
            )

    def open(self, path: str) -> DataFile:
        """打开一个数据文件

        Args:
            path: 文件在仓库中的相对路径

        Returns:
            DataFile 对象, 支持上下文管理器
        """
        if not self._cloned:
            self.pull()
        return DataFile(self, path)

    def _mark_changed(self, path: str) -> None:
        """标记文件已变更 (由 DataFile 调用)"""
        if path not in self._changed_files:
            self._changed_files.append(path)

    def _has_staged_changes(self) -> bool:
        """检查暂存区是否有变更"""
        result = _run_git(
            ["diff", "--cached", "--quiet"],
            cwd=self._repo_dir,
            check=False,
        )
        return result.returncode != 0

    def push(self, commit_msg: str | None = None) -> None:
        """提交并推送变更

        普通模式下, 如果 push 因远程更新而失败, 会自动 pull --rebase 后重试,
        最多重试 MAX_PUSH_RETRIES 次.

        Args:
            commit_msg: 提交消息, 为 None 则使用预设消息

        Raises:
            RuntimeError: 重试耗尽后仍然失败
        """
        if not self._cloned:
            return

        msg = commit_msg or self._commit_msg

        _run_git(["add", "-A"], cwd=self._repo_dir)

        if not self._has_staged_changes():
            logger.debug("没有变更, 跳过提交")
            self._changed_files.clear()
            return

        if self._only:
            self._push_only(msg)
        else:
            self._push_normal(msg)

        self._changed_files.clear()
        self._commit_msg = DEFAULT_COMMIT_MSG

    def _push_only(self, msg: str) -> None:
        """only 模式推送: 创建孤立提交并 push -f"""
        _run_git(["checkout", "--orphan", "_hx_git_db_temp"], cwd=self._repo_dir)
        _run_git(["add", "-A"], cwd=self._repo_dir)
        _run_git(["commit", "-m", msg], cwd=self._repo_dir)

        _run_git(
            ["branch", "-D", self._branch],
            cwd=self._repo_dir,
            check=False,
        )
        _run_git(["branch", "-m", self._branch], cwd=self._repo_dir)
        _run_git(["push", "origin", self._branch, "--force"], cwd=self._repo_dir)

    def _push_normal(self, msg: str) -> None:
        """普通模式推送: commit + push, 冲突时自动 rebase 重试"""
        _run_git(["commit", "-m", msg], cwd=self._repo_dir)

        for attempt in range(1, MAX_PUSH_RETRIES + 1):
            result = _run_git(
                ["push", "origin", self._branch],
                cwd=self._repo_dir,
                check=False,
            )
            if result.returncode == 0:
                return

            logger.warning(
                "push 失败 (第 %d/%d 次), 尝试 rebase 后重试...",
                attempt, MAX_PUSH_RETRIES,
            )

            rebase_result = _run_git(
                ["pull", "--rebase", "origin", self._branch],
                cwd=self._repo_dir,
                check=False,
            )

            if rebase_result.returncode != 0:
                logger.error("rebase 出现冲突, 中止 rebase 并重置")
                _run_git(["rebase", "--abort"], cwd=self._repo_dir, check=False)
                _run_git(["reset", "--hard", f"origin/{self._branch}"], cwd=self._repo_dir, check=False)
                _run_git(["add", "-A"], cwd=self._repo_dir)
                if self._has_staged_changes():
                    _run_git(["commit", "-m", msg], cwd=self._repo_dir)
                else:
                    logger.info("rebase 后无变更, 跳过")
                    return

            if attempt < MAX_PUSH_RETRIES:
                time.sleep(RETRY_DELAY * attempt)

        raise RuntimeError(
            f"push 到 {self._display_url} ({self._branch}) 在 {MAX_PUSH_RETRIES} 次重试后仍然失败"
        )

    def cleanup(self) -> None:
        """清理临时目录"""
        if self._is_temp and os.path.exists(self._work_dir):
            shutil.rmtree(self._work_dir)
            logger.debug("已清理临时目录: %s", self._work_dir)

    def __enter__(self) -> DataBase:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """退出时自动推送变更并清理"""
        if exc_type is None and self._changed_files:
            self.push()
        self.cleanup()

    def __repr__(self) -> str:
        mode = "only" if self._only else "normal"
        return f"DataBase({self._display_url!r}, branch={self._branch!r}, mode={mode})"
