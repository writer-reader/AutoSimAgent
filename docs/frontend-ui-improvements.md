# 前端界面改进方案

**日期：** 2026-07-09  
**现状：** React 18 + Vite + Tailwind v3 + shadcn/ui，基础功能跑通  
**目标：** 接近 Claude 网页端风格：简洁白色调、清晰文字层级、宽松间距

---

## 已完成

- [x] 基准字号从 16px → **15px**，行高 1.65，`antialiased` 字体渲染（commit `e854d45`）

---

## 待改动清单

### 1. 全局字体替换

**现状：** 无显式字体，浏览器默认 San Francisco / Segoe UI  
**目标：** Geist（Claude 使用的同款现代 sans，Next.js 官方）

```css
/* index.css 或 App.tsx 引入 */
@import url('https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&display=swap');

html {
  font-family: 'Geist', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
```

或通过 npm 安装（推荐，无 Google Fonts 依赖）：

```bash
npm install geist
```

```tsx
// main.tsx
import 'geist/dist/geist.css'
```

---

### 2. 颜色体系微调

**现状：** shadcn 默认 slate 调色板，偏蓝灰  
**目标：** Claude 风格：更接近纯中性灰，accent 收敛到单色

修改 `index.css` CSS variables：

```css
:root {
  /* 背景层级（从白到浅灰） */
  --background: 0 0% 100%;           /* 纯白 */
  --card: 0 0% 98%;                  /* 极浅灰卡片背景 */
  
  /* 文字层级 */
  --foreground: 0 0% 9%;             /* 近黑，不用纯黑 */
  --muted-foreground: 0 0% 45%;      /* 次要文字，中灰 */
  
  /* 边框：更轻 */
  --border: 0 0% 89%;                /* 浅灰边框 */
  --input: 0 0% 89%;
  
  /* 圆角：统一 8px */
  --radius: 0.5rem;
}
```

---

### 3. Header 布局优化

**现状：** Header 有 `border-b` + 步骤指示器居中 + 左右空占位  
**问题：** 步骤指示器文字偏小，整体偏窄

**改动：**
- 增加 Header 高度：`py-3` → `py-4`
- 步骤标签加 `text-sm font-medium`
- 品牌名增大：`text-lg font-semibold`
- 最大宽度限制：`max-w-4xl mx-auto`

---

### 4. Step 1 导入页宽度和间距

**现状：** `max-w-lg mx-auto mt-16`  
**问题：** 偏窄，mt 偏大导致内容浮在中间

**改动：**
```tsx
// 改为
<div className="max-w-md mx-auto mt-12 space-y-5">
```
- 拖拽区高度从 `p-8` → `py-10 px-8`
- 路径输入框加 `h-10`（Claude 输入框高度）

---

### 5. Step 2 流水线面板

**现状：** 阶段进度条节点文字 `text-[10px]`，日志区 `h-64 font-mono`  
**问题：** 进度条文字太小，日志区高度固定

**改动：**

**进度条：**
```tsx
// text-[10px] → text-xs（12px）
// 节点间距 gap-1 → gap-2
```

**日志区：**
```tsx
// h-64 → min-h-[16rem] max-h-[28rem]（响应式高度）
// p-3 → p-4
// space-y-1 → space-y-1.5（行间距略宽）
```

**状态徽章：**
```tsx
// 改用圆点 + 文字，无背景色块：
<span className="flex items-center gap-1.5 text-sm text-blue-600">
  <span className="w-1.5 h-1.5 rounded-full bg-blue-500 animate-pulse" />
  运行中
</span>
```

---

### 6. Step 3 结果页

**现状：** 验收标准列表每条直接排列，无区分  
**问题：** 通过/失败视觉差异不足，⬜ 未评估项和 ❌ 失败项难以区分

**改动：**

```tsx
// 通过：绿色左边框
<div className="pl-3 border-l-2 border-green-400">
  ✅ {c.description}
</div>

// 失败：红色左边框  
<div className="pl-3 border-l-2 border-red-300 text-slate-500">
  ❌ {c.description}
</div>

// 未评估：灰色左边框
<div className="pl-3 border-l-2 border-slate-200 text-slate-400">
  ⬜ {c.description}
</div>
```

**流水线失败时全部标准显示说明：**

当 `taskStatus === 'failed'` 且 `finalResult?.verification?.criteria_results` 为空时，所有标准应显示 ⬜（未评估）而非 ❌（失败）：

```tsx
// Step3Result.tsx 中的判断逻辑
const pipelineFailed = status === 'failed' && !result?.verification?.criteria_results?.length
// pipelineFailed 时统一显示 ⬜，不显示 ❌
```

---

### 7. ApprovalDialog 审批弹层

**现状：** 标题 `text-orange-600`，底部两个按钮  
**建议改动：**
- 弹层最大宽度 `max-w-3xl` → `max-w-2xl`（Monaco 编辑器够用）
- 标题区加顶部色条：`<div className="h-1 bg-orange-500 rounded-t-lg" />`（视觉提示）
- "第 N 次审批" 用 `text-slate-400 text-xs`

---

### 8. 全局细节

| 项目 | 当前 | 建议 |
|---|---|---|
| Button 默认圆角 | `rounded-md`（6px） | 保持，与 Claude 一致 |
| 卡片阴影 | 无 / shadcn 默认 | 无阴影，只用边框 `border border-slate-200` |
| 成功色 | `text-slate-600` | `text-emerald-600` |
| 错误色 | `text-red-600` | 保持 |
| 等待审批色 | `text-orange-600` | 保持 |
| 链接/按钮 focus ring | shadcn 默认蓝色 | 保持（无障碍必须） |

---

## 实施顺序建议

1. **字体** - 影响最大，改动最小（Geist 安装 + CSS 一行）
2. **颜色 token** - 全局生效，改 `index.css` CSS variables
3. **Step 3 验收标准分组显示** - 用户最常看到的内容
4. **Step 2 日志区高度** - 运行时体验
5. **其余细节** - 按需迭代

---

## 注意事项

- 项目使用 Tailwind **v3**（非 v4），不要引入 v4 特有语法
- shadcn 组件已自定义（`dialog.tsx` 移除了 X 按钮），改动时注意不要被 `npx shadcn add` 覆盖
- Monaco Editor 通过 `@monaco-editor/react` 懒加载，字体改变不影响编辑器内字体（编辑器有自己的字体设置）
