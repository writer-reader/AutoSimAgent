#!/usr/bin/env python3
"""终端实时监控工具：连接 SSE 流并可视化任务进度，支持在审批点交互干预。

用法：
    python scripts/watch_task.py <task_id>              # 只监控
    python scripts/watch_task.py <task_id> --approve    # 审批点自动通过
    python scripts/watch_task.py <task_id> --reject     # 审批点自动拒绝
    python scripts/watch_task.py <task_id> --interactive  # 审批点交互输入（默认）

也可以先启动任务、再监控：
    python scripts/watch_task.py --start --paper_id=<id> --pdf=<path>
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Iterator

import httpx

BASE_URL = "http://localhost:8000"

# ANSI 颜色
_C = {
    "reset": "\033[0m",
    "bold": "\033[1m",
    "green": "\033[32m",
    "yellow": "\033[33m",
    "cyan": "\033[36m",
    "red": "\033[31m",
    "magenta": "\033[35m",
    "blue": "\033[34m",
    "gray": "\033[90m",
}


def c(color: str, text: str) -> str:
    return f"{_C.get(color, '')}{text}{_C['reset']}"


# ── SSE 客户端 ──────────────────────────────────────────────────────────────

def sse_events(task_id: str) -> Iterator[dict]:
    """生成器：从 /workflow/{task_id}/stream 读取 SSE 事件，逐个 yield dict。"""
    url = f"{BASE_URL}/workflow/{task_id}/stream"
    with httpx.Client(timeout=None) as client:
        with client.stream("GET", url) as resp:
            resp.raise_for_status()
            buf = ""
            for chunk in resp.iter_text():
                buf += chunk
                while "\n\n" in buf:
                    block, buf = buf.split("\n\n", 1)
                    for line in block.splitlines():
                        if line.startswith("data:"):
                            payload = line[5:].strip()
                            if payload:
                                try:
                                    yield json.loads(payload)
                                except json.JSONDecodeError:
                                    pass


# ── 事件渲染 ─────────────────────────────────────────────────────────────────

_STAGE_ICONS = {
    "mineru": "📄",
    "adapter": "🔄",
    "knowledge": "🧠",
    "graph:init": "⚙️",
    "graph:plan": "📋",
    "graph:generate": "✍️",
    "graph:execute": "▶️",
    "graph:verify": "🔍",
    "graph:request_approval": "⏸️",
    "request_approval": "⏸️",
    "done": "✅",
    "error": "❌",
    "resuming": "▶️",
}


def fmt_time(ts: float | None) -> str:
    if ts is None:
        return ""
    return c("gray", time.strftime("%H:%M:%S", time.localtime(ts)))


def render_event(ev: dict) -> str | None:
    t = ev.get("type", "")
    ts = fmt_time(ev.get("ts"))
    stage = ev.get("stage", "")
    icon = _STAGE_ICONS.get(stage, _STAGE_ICONS.get(t, "•"))

    if t == "stage":
        label = ev.get("label", stage)
        return f"{ts} {icon} {c('cyan', label)}"

    if t == "node":
        phase = ev.get("phase", "")
        node = ev.get("node", stage.replace("graph:", ""))
        if phase == "start":
            return f"{ts}   {c('gray', f'→ {node}')}"
        if phase == "done":
            return f"{ts}   {c('gray', f'✓ {node} done')}"

    if t == "knowledge_done":
        n = ev.get("criteria_count", "?")
        return f"{ts} 🧠 {c('green', f'知识抽取完成，验收标准 {n} 条')}"

    if t == "interrupt":
        payload = ev.get("payload", {})
        preview = payload.get("code_preview", "（无预览）")
        code_len = payload.get("code_len", "?")
        lines = [
            "",
            c("bold", "━" * 60),
            f"⏸️  {c('yellow', '等待审批')}  |  生成代码 {code_len} 字符",
            c("bold", "━" * 60),
            c("gray", "--- 代码预览（前500字）---"),
            preview,
            c("gray", "--- 预览结束 ---"),
            "",
        ]
        return "\n".join(lines)

    if t == "resume":
        approved = ev.get("approved", True)
        label = ev.get("label", "")
        color = "green" if approved else "yellow"
        return f"{ts} ▶️  {c(color, label)}"

    if t == "done":
        status = ev.get("status", "")
        result = ev.get("result") or {}
        color = "green" if status == "completed" else "red"
        lines = [
            "",
            c("bold", "━" * 60),
            f"{'✅' if status == 'completed' else '❌'}  {c(color, f'任务{status}')}",
        ]
        if result:
            lines += [
                f"  验证状态: {result.get('verification', {}).get('status', '—')}",
                f"  校准轮次: {result.get('calib_rounds', 0)}",
                f"  工具调用: {result.get('tool_calls', 0)}",
            ]
            code_paths = result.get("code_paths", [])
            if code_paths:
                lines.append("  生成代码:")
                for p in code_paths[-3:]:
                    lines.append(f"    {c('cyan', p)}")
        lines.append(c("bold", "━" * 60))
        return "\n".join(lines)

    if t == "error":
        return f"{ts} ❌ {c('red', ev.get('error', '未知错误'))}"

    if t == "heartbeat":
        return None  # 心跳不打印

    return f"{ts} {c('gray', json.dumps(ev, ensure_ascii=False)[:120])}"


# ── 审批交互 ──────────────────────────────────────────────────────────────────

def handle_interrupt(task_id: str, ev: dict, args: argparse.Namespace) -> None:
    """在审批点根据参数或用户输入决定是否继续。"""
    if args.approve:
        decision = True
        edited_code = None
        print(c("green", "→ 自动通过（--approve）"))
    elif args.reject:
        decision = False
        edited_code = None
        print(c("yellow", "→ 自动拒绝（--reject）"))
    else:
        # 交互模式
        print()
        while True:
            ans = input(c("bold", "审批 [y=通过 / n=拒绝 / e=编辑代码后通过]? ")).strip().lower()
            if ans in ("y", "yes", ""):
                decision = True
                edited_code = None
                break
            elif ans in ("n", "no"):
                decision = False
                edited_code = None
                break
            elif ans == "e":
                print(c("gray", "粘贴替换代码（空行+EOF 结束，Windows: Ctrl+Z Enter; Linux: Ctrl+D）:"))
                lines = []
                try:
                    while True:
                        lines.append(input())
                except EOFError:
                    pass
                edited_code = "\n".join(lines)
                decision = True
                break
            else:
                print("请输入 y/n/e")

    # 调用 resume API
    params: dict = {"approved": str(decision).lower()}
    if edited_code:
        params["edited_code"] = edited_code
    try:
        resp = httpx.post(f"{BASE_URL}/workflow/{task_id}/resume", params=params, timeout=10)
        resp.raise_for_status()
        print(c("gray", f"→ resume OK ({resp.status_code})"))
    except Exception as exc:
        print(c("red", f"→ resume 失败: {exc}"))


# ── 主流程 ───────────────────────────────────────────────────────────────────

def watch(task_id: str, args: argparse.Namespace) -> None:
    print(c("bold", f"\n👁  监控任务 {task_id}  |  {BASE_URL}"))
    print(c("gray", "Ctrl+C 退出（不影响后台任务）\n"))
    interrupted_handled = False
    try:
        for ev in sse_events(task_id):
            line = render_event(ev)
            if line is not None:
                print(line)

            if ev.get("type") == "interrupt" and not interrupted_handled:
                interrupted_handled = True
                handle_interrupt(task_id, ev, args)

            if ev.get("type") in ("done", "error") and ev.get("reason") != "sentinel":
                break
    except KeyboardInterrupt:
        print(c("gray", "\n[监控已退出，后台任务继续运行]"))
    except Exception as exc:
        print(c("red", f"\n连接错误: {exc}"))


def start_and_watch(args: argparse.Namespace) -> None:
    payload = {"paper_id": args.paper_id, "pdf_path": args.pdf, "user_id": args.user_id}
    try:
        resp = httpx.post(f"{BASE_URL}/workflow/start", json=payload, timeout=10)
        resp.raise_for_status()
        task_id = resp.json()["task_id"]
        print(c("green", f"任务已创建: {task_id}"))
    except Exception as exc:
        print(c("red", f"启动失败: {exc}"))
        sys.exit(1)
    watch(task_id, args)


def main() -> None:
    parser = argparse.ArgumentParser(description="control_agent 任务实时监控")
    parser.add_argument("task_id", nargs="?", help="任务 ID（省略时需 --start）")
    parser.add_argument("--start", action="store_true", help="同时启动新任务")
    parser.add_argument("--paper_id", default="", help="--start 时必填")
    parser.add_argument("--pdf", default="", help="PDF 路径（--start 时必填）")
    parser.add_argument("--user_id", default="local")
    parser.add_argument("--approve", action="store_true", help="审批点自动通过")
    parser.add_argument("--reject", action="store_true", help="审批点自动拒绝")
    parser.add_argument("--base_url", default=BASE_URL, help=f"API 地址（默认 {BASE_URL}）")
    args = parser.parse_args()

    global BASE_URL
    BASE_URL = args.base_url.rstrip("/")

    if args.start:
        if not args.paper_id or not args.pdf:
            parser.error("--start 需要 --paper_id 和 --pdf")
        start_and_watch(args)
    elif args.task_id:
        watch(args.task_id, args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
