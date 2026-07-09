# Frontend UI Polish — Design Spec

**日期：** 2026-07-09  
**范围：** 精准打磨（Scope A）— 不动布局结构，只做视觉层提升  
**栈：** React 18 + Vite + Tailwind v3 + shadcn/ui  
**目标：** Claude.ai 风格：柔和底色、去饱和度语义色、implied structure（背景色暗示分组，不靠边框）、双色主题支持

---

## 1. 基础层：CSS Variables + Dark Mode Token

### 1.1 Token 策略

沿用 shadcn/ui 现有 CSS variable 体系（`:root` + `.dark`），统一在 `frontend/src/index.css` 扩充。

**分工：**
- CSS variable 管理 shadcn 组件的语义色（`--background`、`--card`、`--border` 等）；shadcn 组件内部颜色走 `hsl(var(--xxx))`，`dark:` class 覆盖不到这层。
- 组件级自定义 utility class（如 EventLog 的 `bg-slate-50/80`、失败面板的 `bg-rose-50/60`）不在 shadcn token 体系内，直接配对 `dark:` variant 是正确做法，不矛盾。

### 1.2 Light Mode Token（`:root`）

```css
:root {
  /* 背景层级 */
  --background: 0 0% 97.5%;          /* zinc-50，极浅中性灰，非纯白 */
  --card: 0 0% 100%;                  /* 卡片/容器用纯白，与背景形成微弱对比 */

  /* 文字层级 */
  --foreground: 0 0% 9%;             /* 近黑正文 */
  --muted-foreground: 0 0% 45%;      /* 次要文字 */

  /* 边框 */
  --border: 0 0% 89.8%;
  --input: 0 0% 89.8%;

  /* 圆角（shadcn 内部引用） */
  --radius: 0.5rem;

  /* 其余 shadcn token（primary / destructive / accent 等）保持不变 */
}
```

### 1.3 Dark Mode Token（`.dark`）

```css
.dark {
  --background: 240 5% 10%;          /* zinc-900 近似 */
  --card: 240 5% 13%;                /* 略浅于背景，形成层级 */
  --foreground: 0 0% 94%;
  --muted-foreground: 240 4% 55%;
  --border: 240 4% 20%;
  --input: 240 4% 20%;
}
```

### 1.4 主题切换机制

新建 `frontend/src/hooks/useTheme.ts`：

- 读写 `localStorage` 的 `theme` key（`'light'` | `'dark'`）
- 同步切换 `document.documentElement.classList`
- 初始化时：优先 localStorage，fallback `prefers-color-scheme`
- 返回 `{ theme, toggleTheme }`

### 1.5 切换按钮位置

放在 Header 右侧，同时修复现有的 `<div className="w-32" />` 硬编码占位：

```tsx
<header className="...flex items-center justify-between">
  <div className="flex items-center gap-3 flex-1"> {/* 左侧 flex-1 */}
    <span>control-agent</span>
    <span className="w-2 h-2 rounded-full bg-green-500" />
  </div>
  <StepIndicator current={step} />
  <div className="flex-1 flex justify-end">        {/* 右侧 flex-1 */}
    <ThemeToggle />
  </div>
</header>
```

`ThemeToggle`：shadcn `Button variant="ghost" size="icon"` + lucide-react `<Sun size={15} />` / `<Moon size={15} />`（`strokeWidth={1.5}`）。

---

## 2. 字体：Geist

```bash
npm install geist
```

```tsx
// frontend/src/main.tsx — 在第一行 import
import 'geist/dist/geist.css'
```

```css
/* index.css */
html {
  font-family: 'Geist', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
}
```

Monaco 编辑器使用自身字体配置，不受影响。

---

## 3. 圆角体系（Shape Consistency Lock）

全项目统一三档，不混用：

| 用途 | Tailwind class | 实际值 |
|---|---|---|
| 大容器（EventLog、错误面板、拖拽区、Dialog） | `rounded-xl` | 12px |
| 小元素（Badge、Collapsible 触发器、过程详情区） | `rounded-lg` | 8px |
| 交互控件（Button、Input）| `rounded-md` | 6px（shadcn 默认，不改） |
| 状态指示点 | `rounded-full` | 仅此一处 |

---

## 4. 组件级改动

### 4.1 Step2 状态标签

**现在：** `bg-blue-100 text-blue-700` 色块 pill  
**改为：** 小点 + 文字，无背景色块

```tsx
// 运行中
<span className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400">
  <span className="w-1.5 h-1.5 rounded-full bg-blue-400/70 animate-pulse" />
  运行中
</span>

// 等待审批
<span className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400">
  <span className="w-1.5 h-1.5 rounded-full bg-amber-400/70 animate-pulse" />
  等待审批
</span>

// 失败
<span className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400">
  <span className="w-1.5 h-1.5 rounded-full bg-rose-400/70" />
  失败
</span>
```

### 4.2 EventLog

**现在：** `h-64 font-mono border rounded-md bg-slate-50`  
**改为：**

```tsx
<div className="bg-slate-50/80 dark:bg-zinc-800/50 rounded-xl min-h-[14rem] max-h-[26rem] overflow-y-auto p-4 space-y-1.5 text-sm">
```

- 去掉 `border`，背景色暗示分组
- 去掉 `font-mono`，改 `text-sm` 普通字体
- 高度改响应式（`min-h` + `max-h`）
- 暗色：`dark:bg-zinc-800/50`

### 4.3 Step2 失败面板

**现在：** `border border-red-200 bg-red-50`  
**改为：** `bg-rose-50/60 dark:bg-rose-950/30 rounded-xl`（无边框，轻薄背景色）

### 4.4 StageProgress

- `text-[10px]` → `text-xs`（12px）
- 节点间距 `gap-1` → `gap-2`
- 完成态节点 `bg-slate-500 border-slate-500` → `bg-slate-300 border-slate-300`（完成后安静）

### 4.5 Step3 验收标准

去掉 emoji 符号作为主要视觉区分，改用柔和左边框 + 去饱和度文字：

```tsx
// 通过
<div className="pl-3 border-l-2 border-emerald-300/60">
  <span className="text-slate-700 dark:text-slate-300">{c.description}</span>
</div>

// 失败
<div className="pl-3 border-l-2 border-rose-300/50">
  <span className="text-slate-400 dark:text-slate-500">{c.description}</span>
</div>

// 未评估
<div className="pl-3 border-l-2 border-slate-200 dark:border-zinc-700">
  <span className="text-slate-400 dark:text-slate-500">{c.description}</span>
</div>
```

### 4.6 Step1 拖拽区

- 替换 `📄` emoji → lucide-react `<FileUp className="w-8 h-8 text-slate-300 mx-auto mb-3" strokeWidth={1.5} />`
- 拖拽区改 `rounded-xl`（配合圆角体系）

### 4.7 Step 间过渡动画

`App.tsx` 的 `<main>` 加 `key={step}`，触发 Tailwind v3 内置的 `animate-in fade-in`：

```tsx
<main key={step} className="px-6 py-8 animate-in fade-in duration-150">
```

无需引入新依赖。

---

## 5. 不在本次范围内

以下改动被明确排除（Scope A 约束）：

- Step2 双列布局（时间线 + 日志并排）
- StageProgress 改竖向时间线
- ApprovalDialog 顶部语义区重设计
- Dark mode 之外的任何布局结构变化

---

## 6. 实施顺序

1. `npm install geist` + `main.tsx` import
2. `index.css` — `:root` token + `.dark` token + `html { font-family }` 
3. `useTheme.ts` hook + `ThemeToggle` 组件
4. `App.tsx` — Header spacer 修复 + ThemeToggle 插入 + `<main key={step}>`
5. `StageProgress.tsx` — 文字大小 + 间距 + 完成态颜色
6. `EventLog.tsx` — 背景色块 + 去边框 + 去 mono + 响应式高度
7. `Step2Pipeline.tsx` — 状态标签改点式
8. `Step2Pipeline.tsx` — 失败面板去边框
9. `Step3Result.tsx` — 验收标准左边框
10. `Step1Import.tsx` — FileUp 图标替换 + rounded-xl
