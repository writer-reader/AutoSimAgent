# 提供限制根目录的安全文件读取能力。
from __future__ import annotations

from pathlib import Path

from app.core.exceptions import ToolExecutionError


# SafeFileReader 类，封装该模块中的相关状态与行为。
class SafeFileReader:
    # __init__ 方法，初始化实例依赖和默认参数。
    def __init__(self, allowed_root: str | Path) -> None:
        self.allowed_root = Path(allowed_root).resolve()

    # read_text 函数，读取外部资源并返回内容。
    def read_text(self, path: str | Path) -> str:
        target = Path(path).resolve()
        if self.allowed_root not in target.parents and target != self.allowed_root:
            raise ToolExecutionError("file_outside_allowed_root", "File is outside the allowed root")
        return target.read_text(encoding="utf-8")
