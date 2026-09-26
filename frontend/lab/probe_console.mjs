import { chromium } from 'playwright-core'
import fs from 'node:fs'
import path from 'node:path'

const ROOT = 'Y:/AI/myproject/mycontrolagent/control_agent'
const fig1 = fs.readFileSync(path.join(ROOT, 'data/code/generated/task_dbe9b64148a5/fig_1.png'))
const fig2 = fs.readFileSync(path.join(ROOT, 'data/code/generated/task_dbe9b64148a5/fig_2.png'))
const code = fs.readFileSync(path.join(ROOT, 'data/code/generated/task_dbe9b64148a5/gen_8.m'), 'utf8')
const now = Date.now() / 1000

const critDesc = i => [
  '在t=1s启动二次控制后，各DG输出电压恢复至参考值380V',
  '在t=1s启动二次控制后，系统频率恢复至参考值50Hz',
  '集中式方法中，全局电压估计误差||e_v(t)||渐近收敛至零',
  '分布式方法中，局部电压估计误差||e_fi(t)||渐近收敛至零',
][i] ?? `第 ${i + 1} 条验收指标`

const criteria = Array.from({ length: 23 }, (_, i) => ({
  criterion_id: `crit_demo_${i}`, metric: `metric_${i}`, description: critDesc(i),
}))
const criteria_results = criteria.map((c, i) => ({
  criteria_id: c.criterion_id, passed: i < 5, detail: i === 0 ? '稳态误差 4.4e-07' : null,
}))

const task3 = {
  task_id: 'task_demo3', status: 'completed', stage: 'done', error: null,
  criteria,
  result: {
    verification: { criteria_results }, verdict: '5/23 criteria met：复现未全部达标，瓶颈在 L2/L3/校准。',
    code_paths: [`X:/gen_0.m`, `X:/gen_8.m`],
    artifacts: [
      { kind: 'figure', path: 'X:/fig_1.png', label: 'fig_1' },
      { kind: 'figure', path: 'X:/fig_2.png', label: 'fig_2' },
      { kind: 'data', path: 'X:/results.json', label: 'results' },
    ],
    calib_rounds: 2, tool_calls: 31,
  },
}
const task2 = {
  task_id: 'task_demo2', status: 'running', stage: 'graph:plan', error: null, result: null, criteria: null,
}
const taskFail = {
  task_id: 'task_demo2', status: 'failed', stage: 'graph:execute',
  error: 'ToolExecutionError: MATLAB 执行超时（evaluate_matlab_code 150s）', result: null, criteria: null,
}

const sseEvents = (tid) => {
  const t = () => now - 300
  const mk = (seq, obj) => `id: ${seq}\ndata: ${JSON.stringify({ ts: t(), ...obj })}\n\n`
  return [
    mk(1, { type: 'stage', stage: 'mineru', label: 'PDF 解析中（MinerU）' }),
    mk(2, { type: 'stage', stage: 'adapter', label: '结构化适配中' }),
    mk(3, { type: 'stage', stage: 'knowledge', label: '知识抽取中（LLM）' }),
    mk(4, { type: 'knowledge_done', criteria_count: 23, criteria }),
    mk(5, { type: 'llm_call', label: '知识抽取：主抽取（公式/控制器/参数/验收标准）' }),
    mk(6, { type: 'llm_usage', label: '知识抽取：主抽取', prompt_tokens: 14847, completion_tokens: 4967, duration_s: 63.4 }),
    mk(7, { type: 'node', stage: 'graph:plan', node: 'plan', phase: 'start' }),
    mk(8, { type: 'llm_call', label: '规划：生成仿真执行方案' }),
    mk(9, { type: 'llm_usage', label: '规划：生成仿真执行方案', prompt_tokens: 5132, completion_tokens: 944, duration_s: 9.6 }),
    mk(10, { type: 'node', stage: 'graph:plan', node: 'plan', phase: 'done' }),
    mk(11, { type: 'stage', stage: 'graph:plan', label: 'LangGraph 图启动' }),
  ].join('')
}

function mock(page) {
  page.route('**/api/system/status', r => r.fulfill({ json: { ok: true, uptime_s: 86400, pid: 1234, tasks: { running: 1, total: 5 }, matlab_mcp: 'connected', llm: 'deepseek', db: 'ok' } }))
  page.route('**/api/tasks?**', r => r.fulfill({ json: { items: [
    { task_id: 'task_demo3', paper_id: 'paper_ad7bcb47121d', status: 'completed', stage: 'done', error: null, created_at: now - 7200, updated_at: now - 6000 },
    { task_id: 'task_demo2', paper_id: 'paper_ad7bcb47121d', status: 'running', stage: 'graph:plan', error: null, created_at: now - 600, updated_at: now - 10 },
  ], total: 2, offset: 0, limit: 50 } }))
  page.route('**/api/workflow/task_demo3/stream**', r => r.fulfill({ status: 200, headers: { 'content-type': 'text/event-stream' }, body: sseEvents('task_demo3') }))
  page.route('**/api/workflow/task_demo2/stream**', r => r.fulfill({ status: 200, headers: { 'content-type': 'text/event-stream' }, body: sseEvents('task_demo2') }))
  page.route('**/api/workflow/task_demo3/code/**', r => r.fulfill({ body: code, headers: { 'content-type': 'text/plain' } }))
  page.route('**/api/workflow/task_demo3/artifacts/fig_1.png', r => r.fulfill({ body: fig1, headers: { 'content-type': 'image/png' } }))
  page.route('**/api/workflow/task_demo3/artifacts/fig_2.png', r => r.fulfill({ body: fig2, headers: { 'content-type': 'image/png' } }))
  page.route('**/api/workflow/task_demo2', r => r.fulfill({ json: task2 }))
  page.route('**/api/workflow/task_demo3', r => r.fulfill({ json: task3 }))
  page.route('**/api/workflow/task_demo2/restart', r => r.fulfill({ json: taskFail }))
}

const browser = await chromium.launch({ channel: 'chrome', headless: true })
async function shot(name, taskId, vp, dark = false) {
  const ctx = await browser.newContext({ viewport: vp, deviceScaleFactor: 1.5 })
  if (taskId) await ctx.addInitScript(id => sessionStorage.setItem('control_agent_task_id', id), taskId)
  if (dark) await ctx.addInitScript(() => document.documentElement.classList.add('dark'))
  const page = await ctx.newPage()
  mock(page)
  await page.goto('http://localhost:5173/', { waitUntil: 'networkidle' })
  await page.waitForTimeout(1800)
  await page.screenshot({ path: `lab/console_${name}.png`, fullPage: false })
  await ctx.close()
}
await shot('s1_wide', null, { width: 1600, height: 900 })
await shot('s2_wide', 'task_demo2', { width: 1600, height: 900 })
await shot('s3_wide', 'task_demo3', { width: 1600, height: 900 })
await shot('s2_narrow', 'task_demo2', { width: 390, height: 844 })
await shot('s1_dark', null, { width: 1600, height: 900 }, true)
await browser.close()
console.log('done')
