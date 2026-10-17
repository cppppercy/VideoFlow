"""应用运行期临时文件位置，避免依赖受限的系统临时目录。"""

from __future__ import annotations

import os
from pathlib import Path
from tempfile import TemporaryDirectory


def make_temporary_directory(prefix: str) -> TemporaryDirectory[str]:
    """创建一个位于项目工作目录的、退出后可清理的临时目录。"""
    root = Path(os.environ.get("VIDEOFLOW_RUNTIME_DIR", Path.cwd() / ".videoflow-runtime"))
    root.mkdir(parents=True, exist_ok=True)
    return TemporaryDirectory(prefix=prefix, dir=root, ignore_cleanup_errors=True)
