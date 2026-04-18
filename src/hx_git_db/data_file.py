"""RAII 风格的数据文件操作"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .database import DataBase


class DataFile:
    """RAII 风格的数据文件

    支持上下文管理器, 退出时自动将修改写回文件.
    支持文本 / JSON / 二进制三种读写模式.

    用法:
        with db.open("config.json") as f:
            data = f.read_json()
            data["key"] = "value"
            f.write_json(data)
    """

    def __init__(self, db: DataBase, path: str) -> None:
        self._db = db
        self._rel_path = path
        self._abs_path = os.path.join(db.repo_dir, path)
        self._modified = False

    def _ensure_parent_dir(self) -> None:
        """确保父目录存在"""
        parent = Path(self._abs_path).parent
        parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> str:
        """文件的相对路径"""
        return self._rel_path

    @property
    def abs_path(self) -> str:
        """文件的绝对路径"""
        return self._abs_path

    @property
    def exists(self) -> bool:
        """文件是否存在"""
        return os.path.isfile(self._abs_path)

    def read(self, encoding: str = "utf-8") -> str:
        """读取文件文本内容

        Args:
            encoding: 文件编码, 默认 utf-8

        Returns:
            文件内容字符串, 文件不存在则返回空字符串
        """
        if not self.exists:
            return ""
        with open(self._abs_path, "r", encoding=encoding) as f:
            return f.read()

    def read_bytes(self) -> bytes:
        """读取文件二进制内容

        Returns:
            文件内容字节, 文件不存在则返回空字节
        """
        if not self.exists:
            return b""
        with open(self._abs_path, "rb") as f:
            return f.read()

    def read_json(self, encoding: str = "utf-8") -> Any:
        """读取 JSON 文件

        Args:
            encoding: 文件编码, 默认 utf-8

        Returns:
            解析后的 JSON 对象, 文件不存在则返回空字典
        """
        content = self.read(encoding)
        if not content:
            return {}
        return json.loads(content)

    def write(self, content: str, encoding: str = "utf-8") -> None:
        """写入文本内容

        Args:
            content: 要写入的文本
            encoding: 文件编码, 默认 utf-8
        """
        self._ensure_parent_dir()
        with open(self._abs_path, "w", encoding=encoding) as f:
            f.write(content)
        self._modified = True

    def write_bytes(self, content: bytes) -> None:
        """写入二进制内容

        Args:
            content: 要写入的字节
        """
        self._ensure_parent_dir()
        with open(self._abs_path, "wb") as f:
            f.write(content)
        self._modified = True

    def write_json(self, data: Any, encoding: str = "utf-8", indent: int = 2) -> None:
        """写入 JSON 数据

        Args:
            data: 要序列化的数据
            encoding: 文件编码, 默认 utf-8
            indent: JSON 缩进, 默认 2
        """
        self.write(json.dumps(data, ensure_ascii=False, indent=indent) + "\n", encoding)

    def delete(self) -> None:
        """删除文件"""
        if self.exists:
            os.remove(self._abs_path)
            self._modified = True

    @property
    def modified(self) -> bool:
        """文件是否被修改过"""
        return self._modified

    def __enter__(self) -> DataFile:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """退出上下文时, 如果文件被修改则通知数据库标记变更"""
        if self._modified:
            self._db._mark_changed(self._rel_path)
        return None

    def __repr__(self) -> str:
        return f"DataFile({self._rel_path!r})"
