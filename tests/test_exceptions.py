# 测试文件，用于验证对应模块的基础行为和接口契约。
from __future__ import annotations

from app.core.exceptions import ConfigError


# test_public_error_dict_hides_internal_details 测试函数，验证目标行为符合预期。
def test_public_error_dict_hides_internal_details() -> None:
    error = ConfigError("config_missing", "Required config file is missing", {"file": "secret/path"})

    assert error.to_public_dict() == {
        "code": "config_missing",
        "message": "Required config file is missing",
        "retryable": False,
    }
