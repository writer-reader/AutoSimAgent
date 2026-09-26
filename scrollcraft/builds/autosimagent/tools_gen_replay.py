# -*- coding: utf-8 -*-
"""从 data/autoagent.db 生成落地页回放数据 assets/replay.js。
task_dbe9b64148a5 的真实事件流，策展只做压缩与聚合；所有时间戳/token/计数为真实记录。"""
import sqlite3, json, time, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[3]
B = ROOT / 'scrollcraft/builds/autosimagent'
TID = 'task_dbe9b64148a5'

db = sqlite3.connect(ROOT / 'data/autoagent.db'); db.row_factory = sqlite3.Row
evs = [dict(r) for r in db.execute('select * from events where task_id=? order by seq', (TID,))]
task = dict(db.execute('select * from tasks where task_id=?', (TID,)).fetchone())
by = {e['seq']: e for e in evs}
t0 = task['created_at']

def hmms(ts): return time.strftime('%H:%M:%S', time.localtime(ts))
def fmt(n): return format(n, ',')

c_calls = c_pt = c_ct = 0; crit = 0
metrics = {}
for e in evs:
    p = json.loads(e['payload']) if e['payload'] else {}
    if e['type'] == 'llm_call': c_calls += 1
    if e['type'] == 'llm_usage':
        c_pt += p.get('prompt_tokens') or 0; c_ct += p.get('completion_tokens') or 0
    if (e['type'] in ('node', 'knowledge_done')) and p.get('criteria_count'): crit = p['criteria_count']
    metrics[e['seq']] = (c_calls, c_pt + c_ct, crit, round(e['created_at'] - t0, 1))

def label_of(seq):
    return json.loads(by[seq]['payload']).get('label', '')

def usage_sub(seq):
    p = json.loads(by[seq]['payload'])
    return '↑%s ↓%s tok · %ss' % (fmt(p.get('prompt_tokens', 0)), fmt(p.get('completion_tokens', 0)), p.get('duration_s'))

def agg_usage(seq_a, seq_b):
    us = [json.loads(by[s]['payload']) for s in range(seq_a, seq_b + 1) if s in by and by[s]['type'] == 'llm_usage']
    if not us: return None, None, 0
    label = json.loads(by[seq_a]['payload']).get('label', '审核')
    pt = sum(u.get('prompt_tokens') or 0 for u in us); ct = sum(u.get('completion_tokens') or 0 for u in us)
    dur = round(sum(u.get('duration_s') or 0 for u in us), 1)
    return '%s ×%d' % (label, len(us)), '↑%s ↓%s tok · Σ%ss' % (fmt(pt), fmt(ct), dur), len(us)

def verdict_of(seq):
    p = json.loads(by[seq]['payload']) if by[seq]['payload'] else {}
    return (p.get('verdict') or {}).get('summary', '')

PHASES = []
CUR = None
def phase(pid, span, label, caption):
    global CUR
    CUR = {'id': pid, 'span': span, 'label': label, 'caption': caption, 'lines': []}
    PHASES.append(CUR)

def add(seq, kind, text=None, sub=None, node=None, rb=None, panel=None):
    e = by[seq]
    calls, tok, cr, el = metrics[seq]
    CUR['lines'].append({'k': kind, 't': hmms(e['created_at']),
                         'x': text if text is not None else label_of(seq),
                         's': sub, 'node': node, 'rb': rb, 'panel': panel,
                         'c': {'calls': calls, 'tok': tok, 'crit': cr, 'el': el}})

phase('ingest', 1.3, '阶段 01 · 解析与知识抽取',
      'MinerU 把 PDF 拆成结构化文本，LLM 从中提取公式、参数、控制器与验收标准。日志逐条记录每次调用的 token 与耗时。')
add(119, 'stage', 'PDF 解析中（MinerU）', node='parse')
add(120, 'stage', '结构化适配中', node='parse')
add(121, 'stage', '知识抽取中（LLM）', node='knowledge')
add(122, 'call', node='knowledge')
add(123, 'usage', sub=usage_sub(123), node='knowledge')
add(124, 'usage', sub=usage_sub(124), node='knowledge')
add(125, 'know', '知识抽取完成，10 条验收标准', node='knowledge', panel='knowledge')

phase('plan', 1.6, '阶段 02 · 规划与生成',
      '图规划执行方案，按论文的控制器结构生成 MATLAB 脚本；auto_approve=false 时执行前暂停，等人工审批。')
add(126, 'stage', '初始化 LangGraph + MATLAB MCP', node='plan')
add(129, 'call', node='plan')
add(130, 'usage', sub=usage_sub(130), node='plan')
add(133, 'call', node='generate')
add(134, 'usage', sub=usage_sub(134), node='generate')
add(135, 'artifact', 'gen_0.m 已生成（8,594 字节）', node='generate', panel='code')
add(137, 'interrupt', '等待人工审批：MATLAB 代码已生成，请审核后 resume', node='approval', panel='approval')
add(138, 'resume', '恢复执行：批准执行', node='execute', panel='approve-ok')

phase('round1', 2.0, '阶段 03 · 执行与验收',
      '生成的代码交给本地 MATLAB（MCP）执行，结果对照验收标准逐条评审。执行受阻先自救，仍未达标则回滚。')
add(141, 'node', '执行节点启动（MATLAB via MCP）', node='execute')
add(143, 'retry', '执行受阻，L2 回滚：重新生成代码', node='generate', rb='L2')
add(145, 'usage', sub=usage_sub(145), node='generate')
add(149, 'retry', '再次 L2 回滚：重生成', node='generate', rb='L2')
add(151, 'usage', sub=usage_sub(151), node='generate')
add(155, 'node', '验收节点启动：评审 ×5 + 硬编码/作弊检查', node='verify')
add(157, 'usage', sub=usage_sub(157), node='verify')
add(161, 'usage', sub=usage_sub(161), node='verify')
add(165, 'usage', sub=usage_sub(165), node='verify')
add(167, 'usage', sub=usage_sub(167), node='verify')
add(168, 'verdict-fail', '✗ 验收未达标（%s）' % verdict_of(168), node='verify', panel='verdict-fail')
add(168, 'rollback', 'L2 回滚 → 重新生成代码', node='generate', rb='L2')

phase('rollback', 1.6, '阶段 04 · L2 / L3',
      '重生成代码、重规划方案。每一次回滚都是图上的一条边，记录在事件流里。')
add(170, 'call', '代码生成（第 4 版）', node='generate')
add(171, 'usage', sub=usage_sub(171), node='generate')
add(173, 'node', '执行完成', node='execute')
add(175, 'rollback', 'L3 回滚 → 重新规划', node='plan', rb='L3')
add(177, 'usage', sub=usage_sub(177), node='plan')
add(180, 'call', '代码生成（第 5 版）', node='generate')
add(181, 'usage', sub=usage_sub(181), node='generate')
add(183, 'node', '执行完成', node='execute')
tx, sx, nc = agg_usage(186, 195)
add(195, 'call', tx, sub=sx, node='verify')
add(198, 'verdict-fail', '✗ 第二轮验收未达标', node='verify', panel='rounds')
add(198, 'rollback', 'L4 回滚 → 重新抽取知识', node='knowledge', rb='L4')

phase('l4', 2.0, '阶段 05 · L4 深度重抽取',
      '回滚到最上游：重新抽取知识，穷尽采样验收标准并归并去重，10 条变 23 条。')
add(205, 'node', '知识重抽取启动（L4）', node='knowledge', rb='L4', panel='l4')
add(206, 'call', '知识抽取：主抽取（重跑）', node='knowledge')
add(207, 'usage', sub=usage_sub(207), node='knowledge')
add(208, 'usage', sub=usage_sub(208), node='knowledge')
add(209, 'call', node='knowledge')
add(210, 'usage', sub=usage_sub(210), node='knowledge')
add(211, 'call', node='knowledge')
add(212, 'usage', sub=usage_sub(212), node='knowledge')
add(213, 'call', node='knowledge')
add(214, 'usage', sub=usage_sub(214), node='knowledge')
add(215, 'call', node='knowledge')
add(216, 'usage', sub=usage_sub(216), node='knowledge')
add(218, 'diff', '验收标准归并完成：10 → 23 条', node='knowledge', panel='criteria-diff')

phase('decisive', 1.4, '阶段 06 · 决胜轮',
      '新标准下连续两轮重生成与验收，节奏加快。')
add(221, 'usage', sub=usage_sub(221), node='plan')
add(224, 'call', '代码生成（第 6 版）', node='generate')
add(225, 'usage', sub=usage_sub(225), node='generate')
add(227, 'node', '执行完成', node='execute')
tx, sx, nc = agg_usage(230, 249)
add(249, 'call', tx, sub=sx, node='verify')
add(252, 'verdict-fail', '✗ 第三轮未达标', node='verify', panel='rounds')
add(252, 'rollback', 'L2 回滚 → 重生成', node='generate', rb='L2')
add(255, 'usage', sub=usage_sub(255), node='generate')
add(257, 'node', '执行完成', node='execute')
tx, sx, nc = agg_usage(260, 279)
add(279, 'call', tx, sub=sx, node='verify')
add(282, 'verdict-fail', '✗ 第四轮未达标', node='verify', panel='rounds')
add(282, 'rollback', 'L2 回滚 → 重生成（第 9 版）', node='generate', rb='L2')

phase('final', 3.0, '阶段 07 · 最后一轮',
      '第 9 版代码交给 MATLAB，两张仿真图落盘。结算：5/23 达标，每一步留痕。')
add(285, 'usage', sub=usage_sub(285), node='generate')
add(287, 'node', '执行完成，产物落盘', node='execute')
add(291, 'usage', sub=usage_sub(291), node='verify')
add(293, 'usage', sub=usage_sub(293), node='verify')
add(295, 'usage', sub=usage_sub(295), node='verify')
add(297, 'usage', sub=usage_sub(297), node='verify')
add(299, 'usage', sub=usage_sub(299), node='verify')
add(301, 'usage', sub=usage_sub(301), node='verify')
add(303, 'usage', sub=usage_sub(303), node='verify')
add(305, 'usage', sub=usage_sub(305), node='verify')
add(307, 'usage', sub=usage_sub(307), node='verify')
add(309, 'usage', sub=usage_sub(309), node='verify')
add(311, 'usage', sub=usage_sub(311), node='verify')
add(312, 'verdict-final', '验收结算：5/23 达标', node='verify', panel='final')
add(313, 'done', '✅ 流水线完成（验收未达标 · 结论如实记录）', node='verify', panel='final')

# —— boot 态（greet，恒显于日志顶部） ——
boot = [
    {'k': 'boot', 't': hmms(t0), 'x': '任务已创建 · paper_ad7bcb47121d 已载入', 's': None,
     'c': {'calls': 0, 'tok': 0, 'crit': 0, 'el': 0}},
    {'k': 'boot', 't': hmms(t0), 'x': '流水线待启动', 's': None,
     'c': {'calls': 0, 'tok': 0, 'crit': 0, 'el': 0}},
]

k = json.load(open(ROOT / 'data/knowledge/merged/paper_ad7bcb47121d.json', encoding='utf-8'))
crit_list = json.loads(task['criteria'])
code_head = '\n'.join(open(ROOT / 'data/code/generated/task_dbe9b64148a5/gen_0.m', encoding='utf-8', errors='ignore').read().splitlines()[:24])

TOTALS = {'calls': c_calls, 'prompt': c_pt, 'completion': c_ct, 'tokens': c_pt + c_ct,
          'events': len(evs), 'duration': round(task['updated_at'] - t0, 1),
          'criteria_0': 10, 'criteria_1': 23, 'passed': 5, 'code_files': 9, 'figures': 2,
          'equations': len(k.get('equations', [])), 'parameters': len(k.get('parameters', [])),
          'controllers': len(k.get('controllers', []))}

PAPER = {'title': 'Event-Triggered Updating Method in Centralized and Distributed Secondary Controls for Islanded Microgrid Restoration',
         'id': 'paper_ad7bcb47121d', 'parser': 'MinerU', 'task': TID}

def js(v): return json.dumps(v, ensure_ascii=False)

with open(B / 'assets/replay.js', 'w', encoding='utf-8') as f:
    f.write('// 由 tools_gen_replay.py 生成：data/autoagent.db 中 task_dbe9b64148a5 的真实事件回放。\n')
    f.write('window.REPLAY = {\n')
    f.write('  paper: %s,\n' % js(PAPER))
    f.write('  totals: %s,\n' % js(TOTALS))
    f.write('  boot: %s,\n' % js(boot))
    f.write('  knowledge: {equations: %d, parameters: %d, controllers: %d, criteria: %s},\n'
            % (TOTALS['equations'], TOTALS['parameters'], TOTALS['controllers'],
               js([{'id': c['criterion_id'], 'metric': c.get('metric', ''), 'desc': c.get('description', '')} for c in crit_list[:4]])))
    f.write('  codeHead: %s,\n' % js(code_head))
    f.write('  phases: [\n')
    for ph in PHASES:
        f.write('    %s,\n' % js(ph))
    f.write('  ],\n};\n')

print('phases:', [(p['id'], p['span'], len(p['lines'])) for p in PHASES])
print('totals:', TOTALS)
