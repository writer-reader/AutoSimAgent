# AutoSimAgent 开发进度与交接（截至 2026-09-26）

> 新会话接手方式：先读这份文档。最新交接来源：2026-09-25~26 会话 **sess_880aec49-0ac4-4213-8eb5-5c0e97281a4e**
> （落地页 + 控制台改造 + git 三连提交，见下方两段"追加"）。
> 前序文档由 2026-09-25 会话（sess_6d558f28-b69b-4197-a730-00b820945c0b）生成，覆盖当天的后端改动、踩坑记录。
>
> **追加（2026-09-25 晚，产品官网落地页会话）**：
> - 用 scroll-craft 技能做出产品官网落地页：**Live surface 语法**——整页是产品台面本身，滚动=时间轴，
>   完整回放 `data/autoagent.db` 里 task_dbe9b64148a5 的 195 条真实事件（63 次 LLM 调用 / 318,376 tokens /
>   20:14 / 5-23 验收结论如实呈现，含「作弊嫌疑」真实评审理由）。
> - 构建：`scrollcraft/builds/autosimagent/`（BRIEF.md + 引擎 + tools_gen_replay.py 回放数据生成器 + lab/ 验收截图）；
>   发布：`frontend/public/landing/`（纯静态，dev 下访问 `/landing/index.html`；App 头部已加「产品主页」链接）。
> - 签名动作：回滚 playhead——滚动向前、流水线图播放头沿 L2/L3/L4 回滚边倒退，图节点可点击跳转（即导航）。
> - 验收：桌面/移动(390)/减动效三套 shoot 全绿（无 dead scroll、无控制台错误、无失败请求）；对比度手动核算 ≥4.5:1。
> - 新增仓库根 `.scrollcraft.json`（scrollcraft 工作区指向 `scrollcraft/`）；FINGERPRINTS.md 已追加首行。
> - 踩坑：Vite dev 对 `/landing/` 目录 URL 走 SPA 回退，必须用 `/landing/index.html`；
>   引擎 CSS 有 `html{scroll-behavior:smooth}`，编程滚动会途经中间阶段，回放控制器的状态要在 meta=null（boot 区）时显式复位。
>
> **追加（2026-09-26，控制台 UI 改造）**：
> - 布局：外壳 `max-w-6xl→max-w-7xl`，main 去掉 `max-w-3xl` 改流宽；Step1 窄表单居中（max-w-xl），Step2 双栏工作台
>   （左=运行监控+中断/失败卡，右=事件日志 sticky 满高，xl+ 生效），Step3 双栏（左=验收结论+产物，右=最终代码+过程记录）。
> - 新建任务一键化：store 新增 `startNewTask()`（clearTask+清 Step1 残留+setStep(1)），入口=header 按钮 / 侧栏顶部 / 失败卡 / Step3 底部。
> - 视觉：StageProgress 图标节点+整体进度条；RunMonitor 统计瓦片（阶段/LLM/Token/错误）；Step3 验收结论配 CheckCircle2/XCircle
>   与达标徽章、总结卡配图标；header 加 Bot logo；Step2 标题随状态自适应。全部用已有 lucide 依赖，零新包。
> - 顺手修：切步时 window 回顶（CodePanel 会把页面滚到中部）。
> - 踩坑：Vite dev 长会话会提供过期模块转换（白屏 `startNewTask is not defined` 但磁盘文件正确）——touch 源文件或重启 dev server 即愈。
> - 验证：tsc 通过；无头 Chrome 用真实任务（cb34c92183d1/dbe9b64148a5）截宽/窄/暗 6 帧确认布局与对比度（截图在 scrollcraft/builds/autosimagent/frontend/lab/）。

> **追加（2026-09-26，Step3 结果页卡片化验收报告）**：
> - 三板块卡片化：验收结论 / 仿真产物 / 最终代码 / 过程记录各成一张带卡片头的有边界卡片（CardShell，可折叠），不再是裸标题漂在留白里。
> - 验收结论卡：大号得分头图 + 绿/红分段比例条 + 图例（达标/未达标/作弊嫌疑 N）；逐条明细取自最后一次 verify 结算事件的 verdict.results
>   （真实 expected/actual/reason/hardcoded），未达标行带指标 chip + 期望实测 + 琥珀色「作弊嫌疑」徽标 + 评审理由，达标行紧凑单行。
> - 仿真产物卡：每图带「图 N」编号徽标 + 真实 MATLAB 图题（前端从最终版 gen_N.m 源码解析 title('...') → fig_N.png，extractFigureTitles）+
>   文件名 chip + 「原图」链接 + 出处说明（由最终版 gen_8.m 绘制）。
> - 数据修复：恢复/刷新路径曾只认 status=completed 才进结果页（failed-with-result 任务回不到 Step3），现统一为「有 result 即直达」（restoreSettled）；
>   并经 /tasks/{id}/events 回放端点补拉全部事件归档进 eventLog（fetchFinalVerdict），恢复路径的统计条（20m14s / 66 次 / 318,376 tok / 4 次受阻）
>   与过程记录卡（195 条事件）与 live 路径同源为真实数字。原「5/10 达标」显示 bug 一并消除（L4 扩充后实际 5/23）。
> - 追加：左侧「任务记录」加边界但刻意不用结果卡的语言——小标签留在面板外，列表放着色内嵌面板
>   （rounded-lg + bg-slate-100/70，无边框无头栏），活跃项浮起为白底描边 pill；侧栏是导航件，右侧是内容卡，两种格式。
> - 新建任务入口收敛为唯一一个（任务记录侧栏顶部）：移除 header 按钮、Step2 中断/失败卡与 Step3 底部的三个入口（store.startNewTask 保留）。
> - 出图张数改为模型自判：_FIGURE_SAVE_HINT 不再举例「fig_1.png、fig_2.png」两张，改为「按验收标准自主挑关键图、宁缺毋滥，
>   按 fig_N 顺序命名，每图必须先 title() 写明内容」（title 约定同时喂给前端 extractFigureTitles 的图题解析）；产物扫描/前端展示本就不限张数。
> - 验证：tsc + vitest 14 通过；Playwright 用真实 DB 导出 fixture（lab/step3_fixture.json + probe_step3.mjs）走真实恢复路径，亮/暗/窄 6 帧验收通过。
> - 踩坑：Vite 8（oxc）解析不了 ternary 里 && 嵌 fragment 的 JSX（tsc 能过），压平成字符串即可；5173 上的旧 dev server 会供过期模块，验收请用新起的实例。

## 一、当前状态

- 后端 `python run_backend.py` → http://127.0.0.1:8000；前端 `cd frontend && npm run dev` → http://localhost:5173
- 后端测试 **57 个全部通过**；前端 tsc 无错误
- **git 未提交**（用户明确要求先不提交）：工作区含上一批 M0 改动（事件持久化/系统监测/任务恢复）+ 本日全部改动
- 事件库 `data/autoagent.db`：有真实任务记录（含一次端到端跑通：66 次 LLM 调用、31.8 万 tokens、2 张仿真图，验收 5/23 达标）
- 论文 `paper_ad7bcb47121d` 的知识缓存已删除——下次运行会用新 prompt 重新抽取（输出中文）

## 二、本日完成的改动

### 后端
1. **LLM 性能改造**（configs/model.yaml、knowledge.yaml、app/llm/client.py）
   - `criteria_samples: 3→1`（首次只跑主抽取；L4 回滚时升到 3 采样+归并，采样温度 0.5）
   - `request_timeout_s: 600→150`；新增 `sdk_max_retries: 1`（显式传给 OpenAI SDK）
   - `extra_body: {enable_thinking: false}` 关思考模式——**必须走 SDK 的 `extra_body=` 形参**，不能 `**` 展开（会 TypeError）
   - prompt 对齐：表格 HTML 单块截断 800 字符；全局上限 = `max_context_tokens × 4`
2. **透明化事件**：每次 LLM 调用发 `llm_call`（带语义标签），结束发 `llm_usage`（prompt/completion/total tokens + 耗时）
   - 机制：`app/events/context.py` 的 contextvar，orchestrator 在任务线程入口挂 emitter（run/resume/restart 三处，finally 复位）
3. **MATLAB MCP 修复**（configs/matlab.yaml）——之前 `mcp_start_failed` 的根因
   - 删除指向不存在文件的 `--extension-file`；`--matlab-root` 改为真实安装位置 `Y:\matlab`（R2024b）
   - 版本号对齐 v0.12.0；high_risk_tools 对齐真实工具（evaluate_matlab_code/run_matlab_file/run_matlab_test_file）
   - 诊断脚本：`scripts/probe_mcp.py`（连接探针）、`scripts/probe_llm.py`（LLM 对照探针）
4. **恢复链路**：`/workflow/{id}/restart` 放开 `failed` 状态；restart/resume 时清空旧 error 字段
5. **API**：`GET /tasks/{id}` 响应增加 `criteria`；`GET /workflow/{id}/artifacts/{filename}` 产物文件端点（防路径穿越）；
   最终 result 携带 `artifacts` 清单；任务列表排序加 rowid 兜底（同毫秒竞态）

### 前端
1. **任务记录侧栏**（`TaskSidebar.tsx` + App 布局改侧栏+主栏，移动端抽屉）：状态徽标/相对时间/点选恢复到对应步骤
2. **Step3 结果页重建**（OpenHands 式）：总结卡（总耗时/LLM 调用/Token/执行受阻）→ 验收结论（✓/✗）→ 仿真产物图像网格
   → **只显示最终版代码**（code_paths 最后一个）→ 完整过程记录（默认折叠，内嵌 EventLog）
3. **Step2 监控**：RunMonitor 面板（阶段耗时实时计时/LLM 调用/Token 用量/错误汇总）；EventLog 错误红色卡片 + llm_call/llm_usage 行
4. **SSE 健壮性**（useWorkflowStream + store）：lastSeq 断点续传 + streamNonce 强制重连；error 事件不再关流；
   重连后新事件自动清旧失败标记；哨兵 done（无 status）不误跳 Step3；interrupt 恢复待审批状态
5. 失败任务卡片新增「从断点继续」；StageProgress 已完成阶段绿✓、失败红点

## 三、踩坑记录（新会话必读）

| 症状 | 根因 | 教训 |
|---|---|---|
| mcp_start_failed | extension-file 指向不存在文件，server 启动即崩 | MCP 报错先跑 probe 脚本看底层 |
| llm_request_failed 只有一句话 | 供应商参数被 `**` 展开成 SDK kwarg，TypeError 在客户端就抛了 | 供应商参数一律走 `extra_body=`；错误信息已改为携带底层原因 |
| 失败又显示待审批 | restart 没清旧 error + 页面刷新回放旧 error 事件 + 哨兵 done 误跳 Step3 | 前端状态机要区分「历史事件」与「当前态」 |
| 知识抽取卡 10 分钟+ | 600s 超时 × SDK 默认重试 × 5 次串行调用 | 三者叠加最坏 2.5h，现已全部收紧 |

## 四、待办 / 下一步

1. **git 提交**：全部改动未提交，用户确认后 commit + push（remote: writer-reader/AutoSimAgent）
2. **验收标准中文验证**：下次运行知识抽取，确认 description 输出中文（metric 保持英文蛇形）
3. **复现质量**：真实跑通那次只有 5/23 指标达标——瓶颈在复现质量（L2/L3/校准），不是系统故障
4. **论文库 P2**：侧栏二期——`GET /papers`（缓存状态徽标：已解析/已抽取）+ 从论文库直接建任务免重传
5. **scroll-craft 插件**：manifest 缺 `"skills": "skills"` 已手修（缓存路径
   `C:\Users\angry\.zcode\cli\plugins\cache\nateherk\nateherk-design\0.3.0\.claude-plugin\plugin.json`），
   重启会话后应可在技能列表看到；**插件更新会冲掉此修复，需重补**（建议上游提 issue）。
   该技能用于做产品官网落地页；工具型 UI 改造用其设计准则（taste.md：4px 节奏/字距/62ch/Dense 家族）
6. 可选：token 成本换算表（各模型单价配置化）

## 五、服务与端口

- 后端后台进程运行中（端口 8000）；前端 Vite dev（5173，HMR 自动生效，改动前端无需重启）
- 后端重启后：启动扫描会把孤儿 running 任务标 interrupted（awaiting_approval 不动）；
  LangGraph checkpoint 落 sqlite，凭 task_id 可从断点续跑

> **追加（2026-09-26，Phase 1 应用壳 + 路由）**：
> - 引入 react-router-dom v7（history 模式，main.tsx 挂 BrowserRouter）。全局 1-2-3 步指示器退场，阶段感收进任务详情内部。
> - 路由表：/ 工作台（无活动任务 = 新建面板；有 = 当前任务详情）· /tasks/:taskId 任务详情（URL 为唯一事实来源，
>   刷新/分享/侧栏点选共用 loadTaskById 恢复路径，内含 loading 骨架与「任务不存在」态）· /papers 论文库占位（Phase 2）· * 回 /。
> - store：sessionStorage 会话恢复机制整体退役（SESSION_KEY/SESSION_TASK_KEY 删除），selectTask 改名 loadTaskById
>   并在 404 时抛错供页面呈现；restoreSettled 语义不变。侧栏行点击 / 新建任务改由组件内 useNavigate 承担。
> - 左 rail：新建任务（唯一入口）→ 视图导航（工作台/论文库，NavLink 蓝色 tint active 态）→ 任务记录（着色内嵌面板不变）。
> - 新增 src/pages/（PapersPage 占位：三个能力卡 + 「下一阶段上线」徽章）；TaskDetailSkeleton 骨架屏。
> - 验证：tsc + vitest 14 过；Playwright 六帧（/ /tasks/:id /papers 暗色 窄屏 404 态）+ 四步客户端交互
>   （导航点击、任务行、品牌回工作台、新建任务清空）全过，探针 lab/probe_shell.mjs。
> - 注意：/landing/ 与 /tasks/:id 都依赖 SPA fallback（dev 下 Vite 自带；若静态部署需服务端 catch-all）。
> - 注意：/landing/ 与 /tasks/:id 都依赖 SPA fallback（dev 下 Vite 自带；若静态部署需服务端 catch-all）。

> **追加（2026-09-26，任务删除）**：
> - 后端：DELETE /tasks/{task_id}（tasks.py）→ registry.delete → EventStore.delete_task（tasks+events 一并清；运行中 409 拒绝；
>   data/code/generated/<task_id>/ 产物文件保留在磁盘，不在删除范围）。测试 tests/test_task_delete.py。
> - 前端：TaskRow 行尾垃圾桶按钮（lg 悬停显现/触屏常显，两击确认——首击变琥珀警示态 2.6s 内再点才删，超时自动还原）；
>   删当前任务时先 startNewTask+navigate('/') 再发请求；删除后刷新列表。
> - 踩坑：TaskDetailPage 对「已清空的 store + 未变 URL 参数」会重拉已删任务（复活竞态）——loadTaskById 加 AbortSignal +
>   handledRef 仅在未中止的成功加载后标记（StrictMode 双跑下中止的首次加载不得阻断/标记后续加载）。

> **追加（2026-09-26，架构图更新）**：
> - 项目架构图.svg 更新至 09-26（生成脚本 scrollcraft/builds/autosimagent/lab/gen_arch_svg.py，原稿备份 项目架构图_0925备份.svg）：
>   修正 React 18→19；前端层补 AppShell+Router / Step3Result / TaskSidebar / public/landing（双行卡片）；API 层补 DELETE /tasks/{id}；
>   events/store 补 delete_task；工作流补出图张数自判约定；测试标注 18 个 pytest 文件 + 前端 vitest 14 用例；琥珀色图例改为 09-26 未提交。
