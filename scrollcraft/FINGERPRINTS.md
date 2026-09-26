# Fingerprints

Every site you build with **scroll-craft** gets one row here, appended after it
ships. The registry exists so your next build can prove it is a different page
rather than a re-skin of one you already made.

This file is **yours**. It starts empty on purpose: the gate is about not
repeating *yourself*, so it has nothing to say until you have built something.

The rules and the gate live in the skill's
`references/uniqueness.md`. Short version:

**A new build must differ from EVERY row below on at least 4 of the 6
dimensions.** Four against each row individually, not four on average across the
table. If a planned build fails, change the plan. Never edit a row to make room
for it.

The six dimensions are: **grammar**, **nav treatment**, **hero device**,
**act-sequence shape**, **close pattern**, **signature move**.

Dimension 6 is free, because a signature move is unique by definition. So the
gate really asks for three more out of the remaining five, and a build that
changes only grammar and world will fail it.

---

## The registry

| Build | Grammar | Nav treatment | Hero device | Act-sequence shape | Close pattern | Signature move | World | Port |
|---|---|---|---|---|---|---|---|---|

*(empty: your first build has nothing to clear, so build whatever the interview
points at. From the second onwards, this table is the constraint.)*

---

## What is taken

Add a bullet here whenever a build claims something a later build should avoid
reusing: a grammar, a nav treatment, a close pattern, a signature move, an
act-count-and-length band. The shared columns are what the next build inherits
as a constraint, so writing them down is the whole point.

Nothing is taken yet.

---

## Appending a row

After shipping, add one line to the table and one bullet to **What is taken** if
the build claimed something new. Fill every column. Say what the build shares
with existing rows.

Rows are append-only. A build that has been superseded stays in the table,
because the space it occupies is still occupied.

---

## Worked example

The skill's author kept a registry of twelve builds across eight page grammars.
If you want to see what a filled-in table looks like, and which shapes tend to
collide, read `EXAMPLES.md` in the scroll-craft repository. Treat it as
illustration only: those rows are somebody else's builds and they do **not**
constrain yours.

## autosimagent · 2026-09-25

| 维度 | 值 |
|---|---|
| Grammar | Live surface（§2.3）：固定台面 + 空 flow 标记，data-sc-verify-state 发布渲染态 |
| Nav treatment | 应用 chrome 顶栏（wordmark + 回放徽标 + 工作台链接）；流水线图即导航（7 节点可点击跳转） |
| Hero device | Surface already in a state：boot 台面（待机日志 + 归零遥测 + 论文卡），无标题屏 |
| Act-sequence shape | 7 个 flow 标记，12.9vh 回放轨 + 1vh boot + ~1.5vh 收束；无 pin/scrub |
| Close pattern | 真输入框（新建任务表单 → 本地演示队列卡）+ colophon；无磁吸/聚光灯 |
| Signature move | 回滚 playhead：滚动向前、播放头沿回滚边倒退（L2/L3/L4 弧线点亮），图节点即导航 |
| World | 浅色 Dense 工作台（产品自身主题）；零生成素材，全部真实运行数据（data/autoagent.db task_dbe9b64148a5） |
| Port | 构建 scrollcraft/builds/autosimagent → 发布 frontend/public/landing/（dev: /landing/） |
| 与已有行共享 | 无（registry 首行） |
