# 管理生成代码到 verified 目录的基础晋级流程。
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import shutil

from app.core.exceptions import VerificationError


@dataclass
# VerificationResult 类，封装该模块中的相关状态与行为。
class VerificationResult:
    ok: bool
    verified_path: str | None
    reason: str


# CodeVerifierService 类，封装该模块中的相关状态与行为。
class CodeVerifierService:
    # promote_if_verified 函数，将通过校验的产物晋级到目标目录。
    def promote_if_verified(self, generated_path: str, verified_dir: str = "data/code/verified") -> VerificationResult:
        source = Path(generated_path)
        if not source.exists():
            raise VerificationError("generated_code_missing", "Generated code file does not exist")
        output_dir = Path(verified_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        target = output_dir / source.name
        shutil.copy2(source, target)
        return VerificationResult(ok=True, verified_path=str(target), reason="basic_file_check_passed")
