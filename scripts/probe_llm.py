# 临时探针：直连 LLM 复现 llm_request_failed，对比带/不带 extra_body（enable_thinking）的差异。
import json

from app.core.config_loader import load_config
from app.llm.client import LLMClient

cfg = load_config()
msgs = [{"role": "user", "content": "回复一个词：ok"}]


def try_call(name: str, use_extra_body: bool) -> None:
    if use_extra_body:
        cfg.model.extra_body = {"enable_thinking": False}
    else:
        cfg.model.extra_body = {}
    llm = LLMClient(cfg.model)
    try:
        out = llm.complete(msgs, role="planner")
        print(f"[{name}] OK: {out[:60]!r}")
    except Exception as e:
        detail = getattr(e, "detail", None)
        print(f"[{name}] FAIL {type(e).__name__}: {e}")
        if detail:
            print(f"[{name}] detail: {json.dumps(detail, ensure_ascii=False)[:600]}")


try_call("A-带enable_thinking(当前配置)", True)
try_call("B-不带extra_body        ", False)
