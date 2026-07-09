# Frontend UI Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 精准打磨 control-agent 前端视觉层——Geist字体、CSS token双模式、柔和语义色、隐式分组（背景色替代边框）、圆角规范、step间过渡动画。

**Architecture:** 以 shadcn/ui 现有CSS variable体系为基础扩展双模式token；新增 `useTheme` hook管理主题持久化；组件级改动逐文件完成，不动业务逻辑和布局结构。

**Tech Stack:** React 18, Vite, Tailwind v3, shadcn/ui, lucide-react (already installed), vitest + @testing-library/react (jsdom)

## Global Constraints

- Tailwind v3 (NOT v4) — no v4 syntax
- shadcn组件已自定义 (dialog.tsx移除了X按钮)，不要用 `npx shadcn add` 覆盖任何文件
- Monaco Editor字体独立，不受全局字体影响
- lucide-react已安装，统一 strokeWidth={1.5}
- 只改视觉层，不改业务逻辑
- 圆角体系：大容器用 rounded-xl，小元素用 rounded-lg，交互控件用 rounded-md（shadcn默认），状态点用 rounded-full

---

## Task 1: Foundation — Geist font + CSS token system

**Files:**
- Modify: `frontend/package.json` — add `geist` dependency
- Modify: `frontend/src/main.tsx` — add Geist CSS import
- Modify: `frontend/src/index.css` — replace `:root` tokens, add `.dark` tokens, add font-family

**Interfaces:**
- Consumes: current `index.css` with single `:root` block, no `.dark` block, no Geist
- Produces: `index.css` with dual-mode tokens (`--background: 0 0% 97.5%` in light, `--background: 240 5% 10%` in dark), `html { font-family: 'Geist', ... }` declared

**Steps:**

- [ ] Install Geist font package
  ```bash
  cd frontend && npm install geist
  ```
  Expected: `geist` appears in `package.json` dependencies, no errors.

- [ ] Add Geist CSS import to `frontend/src/main.tsx` — insert as the very first import line:
  ```tsx
  import 'geist/dist/geist.css'
  import { StrictMode } from 'react'
  import { createRoot } from 'react-dom/client'
  import './index.css'
  import App from './App.tsx'

  createRoot(document.getElementById('root')!).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
  ```

- [ ] Replace `frontend/src/index.css` with the complete updated file:
  ```css
  @tailwind base;
  @tailwind components;
  @tailwind utilities;

  @layer base {
    :root {
      /* 背景层级 */
      --background: 0 0% 97.5%;
      --card: 0 0% 100%;
      --card-foreground: 222.2 84% 4.9%;
      --popover: 0 0% 100%;
      --popover-foreground: 222.2 84% 4.9%;
      /* 文字层级 */
      --foreground: 0 0% 9%;
      --muted-foreground: 0 0% 45%;
      /* 交互色（保持shadcn默认） */
      --primary: 222.2 47.4% 11.2%;
      --primary-foreground: 210 40% 98%;
      --secondary: 210 40% 96.1%;
      --secondary-foreground: 222.2 47.4% 11.2%;
      --muted: 210 40% 96.1%;
      --accent: 210 40% 96.1%;
      --accent-foreground: 222.2 47.4% 11.2%;
      --destructive: 0 84.2% 60.2%;
      --destructive-foreground: 210 40% 98%;
      /* 边框 */
      --border: 0 0% 89.8%;
      --input: 0 0% 89.8%;
      --ring: 222.2 84% 4.9%;
      --radius: 0.5rem;
    }

    .dark {
      --background: 240 5% 10%;
      --card: 240 5% 13%;
      --card-foreground: 0 0% 94%;
      --popover: 240 5% 13%;
      --popover-foreground: 0 0% 94%;
      --foreground: 0 0% 94%;
      --muted-foreground: 240 4% 55%;
      --primary: 210 40% 98%;
      --primary-foreground: 222.2 47.4% 11.2%;
      --secondary: 240 4% 18%;
      --secondary-foreground: 0 0% 94%;
      --muted: 240 4% 18%;
      --accent: 240 4% 18%;
      --accent-foreground: 0 0% 94%;
      --destructive: 0 62.8% 50%;
      --destructive-foreground: 0 0% 94%;
      --border: 240 4% 20%;
      --input: 240 4% 20%;
      --ring: 240 4.9% 83.9%;
    }
  }

  @layer base {
    html {
      font-size: 15px;
      font-family: 'Geist', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    }
    * { @apply border-border; }
    body {
      @apply bg-background text-foreground;
      line-height: 1.65;
      -webkit-font-smoothing: antialiased;
    }
  }
  ```

- [ ] Verify: start dev server and check visuals
  ```bash
  cd frontend && npm run dev
  ```
  Open browser at `http://localhost:5173`. Verify:
  - Page background is slightly gray (not pure white) — `hsl(0 0% 97.5%)`
  - In DevTools Elements, `html` element has `font-family` including `Geist`
  - Geist font loads in Network tab (geist CSS + woff2 files)

- [ ] Commit
  ```bash
  git add frontend/package.json frontend/package-lock.json frontend/src/main.tsx frontend/src/index.css
  git commit -m "feat(ui): install Geist font, replace CSS token system with dual-mode light/dark"
  ```

---

## Task 2: Theme infrastructure — useTheme hook + ThemeToggle component

**Files:**
- Create: `frontend/src/hooks/useTheme.ts`
- Create: `frontend/src/components/ThemeToggle.tsx`
- Create (test): `frontend/src/hooks/useTheme.test.ts`

**Interfaces:**
- Consumes: `localStorage` key `'theme'` (`'light' | 'dark'`), `document.documentElement.classList`
- Produces:
  - `useTheme(): { theme: Theme, toggleTheme: () => void }` — exported from `@/hooks/useTheme`
  - `<ThemeToggle />` — zero-prop component exported from `@/components/ThemeToggle`
  - `type Theme = 'light' | 'dark'` — named export from `@/hooks/useTheme`

**Steps:**

- [ ] Create `frontend/src/hooks/useTheme.ts`:
  ```typescript
  import { useState, useEffect, useCallback } from 'react'

  export type Theme = 'light' | 'dark'

  function getInitialTheme(): Theme {
    try {
      const stored = localStorage.getItem('theme')
      if (stored === 'light' || stored === 'dark') return stored
      if (window.matchMedia('(prefers-color-scheme: dark)').matches) return 'dark'
    } catch {
      // SSR / no-DOM environment
    }
    return 'light'
  }

  function applyTheme(theme: Theme): void {
    document.documentElement.classList.toggle('dark', theme === 'dark')
    localStorage.setItem('theme', theme)
  }

  export function useTheme() {
    const [theme, setTheme] = useState<Theme>(getInitialTheme)

    useEffect(() => {
      applyTheme(theme)
    }, [theme])

    const toggleTheme = useCallback(() => {
      setTheme(prev => (prev === 'light' ? 'dark' : 'light'))
    }, [])

    return { theme, toggleTheme }
  }
  ```

- [ ] Create `frontend/src/components/ThemeToggle.tsx`:
  ```tsx
  import { Moon, Sun } from 'lucide-react'
  import { Button } from '@/components/ui/button'
  import { useTheme } from '@/hooks/useTheme'

  export function ThemeToggle() {
    const { theme, toggleTheme } = useTheme()
    return (
      <Button
        variant="ghost"
        size="icon"
        onClick={toggleTheme}
        title={theme === 'dark' ? '切换到浅色模式' : '切换到深色模式'}
      >
        {theme === 'dark'
          ? <Sun size={15} strokeWidth={1.5} />
          : <Moon size={15} strokeWidth={1.5} />
        }
      </Button>
    )
  }
  ```

- [ ] Create `frontend/src/hooks/useTheme.test.ts`:
  ```typescript
  import { renderHook, act } from '@testing-library/react'
  import { describe, it, expect, beforeEach, vi } from 'vitest'
  import { useTheme } from './useTheme'

  // Mock matchMedia
  function setupMatchMedia(prefersDark: boolean) {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation((query: string) => ({
        matches: prefersDark && query === '(prefers-color-scheme: dark)',
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })
  }

  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('dark')
    setupMatchMedia(false)
  })

  describe('useTheme', () => {
    it('defaults to light when no localStorage and no system preference', () => {
      const { result } = renderHook(() => useTheme())
      expect(result.current.theme).toBe('light')
    })

    it('reads dark from localStorage', () => {
      localStorage.setItem('theme', 'dark')
      const { result } = renderHook(() => useTheme())
      expect(result.current.theme).toBe('dark')
    })

    it('reads light from localStorage', () => {
      localStorage.setItem('theme', 'light')
      const { result } = renderHook(() => useTheme())
      expect(result.current.theme).toBe('light')
    })

    it('falls back to system dark preference when no localStorage', () => {
      setupMatchMedia(true)
      const { result } = renderHook(() => useTheme())
      expect(result.current.theme).toBe('dark')
    })

    it('toggles from light to dark', () => {
      const { result } = renderHook(() => useTheme())
      expect(result.current.theme).toBe('light')
      act(() => { result.current.toggleTheme() })
      expect(result.current.theme).toBe('dark')
    })

    it('toggles from dark to light', () => {
      localStorage.setItem('theme', 'dark')
      const { result } = renderHook(() => useTheme())
      act(() => { result.current.toggleTheme() })
      expect(result.current.theme).toBe('light')
    })

    it('adds .dark class to documentElement when theme is dark', () => {
      localStorage.setItem('theme', 'dark')
      renderHook(() => useTheme())
      expect(document.documentElement.classList.contains('dark')).toBe(true)
    })

    it('removes .dark class from documentElement when theme is light', () => {
      document.documentElement.classList.add('dark')
      localStorage.setItem('theme', 'light')
      renderHook(() => useTheme())
      expect(document.documentElement.classList.contains('dark')).toBe(false)
    })

    it('persists theme to localStorage on toggle', () => {
      const { result } = renderHook(() => useTheme())
      act(() => { result.current.toggleTheme() })
      expect(localStorage.getItem('theme')).toBe('dark')
    })
  })
  ```

- [ ] Run tests
  ```bash
  cd frontend && npx vitest run src/hooks/useTheme.test.ts
  ```
  Expected: 9 tests pass, 0 failures.

- [ ] Commit
  ```bash
  git add frontend/src/hooks/useTheme.ts frontend/src/hooks/useTheme.test.ts frontend/src/components/ThemeToggle.tsx
  git commit -m "feat(ui): add useTheme hook with localStorage persistence and ThemeToggle component"
  ```

---

## Task 3: App.tsx — Header fix + ThemeToggle + step transition

**Files:**
- Modify: `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `ThemeToggle` from `@/components/ThemeToggle`, `useTheme` side-effect (`.dark` class already applied by Task 2)
- Produces:
  - Header left side: `<div className="flex items-center gap-3 flex-1">` wrapping brand + status dot
  - Header right side: `<div className="flex-1 flex justify-end"><ThemeToggle /></div>` replacing `<div className="w-32" />`
  - Main area: `<main key={step} className="px-6 py-8 animate-in fade-in duration-150">`

**Steps:**

- [ ] In `frontend/src/App.tsx`, add `ThemeToggle` import after the existing imports:
  ```tsx
  import { ThemeToggle } from '@/components/ThemeToggle'
  ```

- [ ] Replace the outer wrapper `<div className="min-h-screen bg-white">` with `<div className="min-h-screen bg-background">` so it picks up the CSS token.

- [ ] Replace the header left-side div (currently `<div className="flex items-center gap-3">`) with a flex-1 variant:
  ```tsx
  <div className="flex items-center gap-3 flex-1">
    <span className="text-slate-800 font-semibold tracking-tight">control-agent</span>
    <span className="w-2 h-2 rounded-full bg-green-500" title="后端在线" />
  </div>
  ```

- [ ] Replace the right-side spacer `<div className="w-32" />` with the ThemeToggle container:
  ```tsx
  <div className="flex-1 flex justify-end">
    <ThemeToggle />
  </div>
  ```

- [ ] Add `key={step}` and transition classes to `<main>`:
  ```tsx
  <main key={step} className="px-6 py-8 animate-in fade-in duration-150">
  ```

- [ ] Verify: run dev server, navigate between steps, observe fade transition. Toggle dark mode button in header — page switches between light/dark. Step indicator stays centered.
  ```bash
  cd frontend && npm run dev
  ```

- [ ] Commit
  ```bash
  git add frontend/src/App.tsx
  git commit -m "feat(ui): fix header spacer, add ThemeToggle, add step fade-in transition"
  ```

---

## Task 4: Pipeline components — StageProgress + EventLog + Step2Pipeline

**Files:**
- Modify: `frontend/src/components/StageProgress.tsx`
- Modify: `frontend/src/components/EventLog.tsx`
- Modify: `frontend/src/steps/Step2Pipeline.tsx`

**Interfaces:**
- Consumes: existing store bindings unchanged (`useAppStore`, `useWorkflowStream`)
- Produces:
  - `StageProgress`: larger label text (`text-xs`), wider gaps (`gap-2`), quieter done-state (`bg-slate-300 border-slate-300`)
  - `EventLog`: borderless rounded-xl container with responsive height and dark-mode background
  - `Step2Pipeline`: dot+text status badge replacing colored pill; borderless rose panel for failure

**Steps:**

- [ ] In `frontend/src/components/StageProgress.tsx`, apply three targeted changes:

  Change 1 — outer flex gap: `gap-1` → `gap-2`
  ```tsx
  // Before
  <div className="flex items-center gap-1 overflow-x-auto py-2 px-4">
  // After
  <div className="flex items-center gap-2 overflow-x-auto py-2 px-4">
  ```

  Change 2 — inner item gap: `gap-1` → `gap-2`
  ```tsx
  // Before
  <div key={stage} className="flex items-center gap-1 shrink-0">
  // After
  <div key={stage} className="flex items-center gap-2 shrink-0">
  ```

  Change 3 — isDone node colors: `bg-slate-500 border-slate-500` → `bg-slate-300 border-slate-300`
  ```tsx
  // Before
  isDone    && 'bg-slate-500 border-slate-500',
  // After
  isDone    && 'bg-slate-300 border-slate-300',
  ```

  Change 4 — label font size: `text-[10px]` → `text-xs`
  ```tsx
  // Before
  className={cn(
    'text-[10px] whitespace-nowrap',
  // After
  className={cn(
    'text-xs whitespace-nowrap',
  ```

- [ ] In `frontend/src/components/EventLog.tsx`, replace the inner scroll container class:
  ```tsx
  // Before
  <div className="h-64 overflow-y-auto p-3 space-y-1 font-mono bg-slate-50 rounded-md border">
  // After
  <div className="min-h-[14rem] max-h-[26rem] overflow-y-auto p-4 space-y-1.5 text-sm bg-slate-50/80 dark:bg-zinc-800/50 rounded-xl">
  ```

- [ ] In `frontend/src/steps/Step2Pipeline.tsx`, replace the status badge `<span>` with the dot+text pattern. Replace the entire `<span className={cn(...)}>` block (lines 33–40 in current file):
  ```tsx
  // Before
  <span className={cn(
    'text-sm font-medium px-2 py-0.5 rounded-full',
    isFailed   && 'bg-red-100 text-red-700',
    isWaiting  && 'bg-orange-100 text-orange-700',
    !isFailed && !isWaiting && 'bg-blue-100 text-blue-700',
  )}>
    {isFailed ? '❌ 失败' : isWaiting ? '⚠️ 等待审批' : '● 运行中'}
  </span>

  // After
  {isFailed && (
    <span className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400">
      <span className="w-1.5 h-1.5 rounded-full bg-rose-400/70" />
      失败
    </span>
  )}
  {isWaiting && (
    <span className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400">
      <span className="w-1.5 h-1.5 rounded-full bg-amber-400/70 animate-pulse" />
      等待审批
    </span>
  )}
  {!isFailed && !isWaiting && (
    <span className="flex items-center gap-1.5 text-sm text-slate-500 dark:text-slate-400">
      <span className="w-1.5 h-1.5 rounded-full bg-blue-400/70 animate-pulse" />
      运行中
    </span>
  )}
  ```

- [ ] In `frontend/src/steps/Step2Pipeline.tsx`, replace the failure panel classes:
  ```tsx
  // Before
  <div className="rounded-md border border-red-200 bg-red-50 p-4 space-y-2">
  // After
  <div className="rounded-xl bg-rose-50/60 dark:bg-rose-950/30 p-4 space-y-2">
  ```

- [ ] Verify: run dev server, navigate to Step2. Status badge shows dot+text (no background pill). EventLog has rounded-xl container without border. In dark mode, EventLog background is `zinc-800/50`.
  ```bash
  cd frontend && npm run dev
  ```

- [ ] Commit
  ```bash
  git add frontend/src/components/StageProgress.tsx frontend/src/components/EventLog.tsx frontend/src/steps/Step2Pipeline.tsx
  git commit -m "feat(ui): StageProgress text/spacing/color, EventLog borderless rounded-xl, Step2 dot badge + rose failure panel"
  ```

---

## Task 5: Result + Import pages — Step3Result + Step1Import

**Files:**
- Modify: `frontend/src/steps/Step3Result.tsx`
- Modify: `frontend/src/steps/Step1Import.tsx`

**Interfaces:**
- Consumes:
  - `Step3Result`: `criteria` array from store, `criteriaMap` keyed by `criteria_id` with `.passed` boolean or undefined
  - `Step1Import`: no new props; `FileUp` from `lucide-react`
- Produces:
  - `Step3Result`: criteria items use left-border pattern (`border-l-2`) instead of emoji prefix; color variants keyed on `passed` value
  - `Step1Import`: `FileUp` icon replaces `📄` emoji; drop zone uses `rounded-xl` with updated padding

**Steps:**

- [ ] In `frontend/src/steps/Step3Result.tsx`, add `FileUp` — wait, this file uses no icons. Add the left-border criteria rendering. Replace the entire criteria `<div>` block inside the `criteria.map()` (currently lines 81–96):
  ```tsx
  // Before
  return (
    <div key={c.criteria_id} className="flex items-start gap-2 text-sm">
      <span className="mt-0.5 shrink-0">
        {res === undefined ? '⬜' : passed ? '✅' : '❌'}
      </span>
      <span className={cn(
        passed === false ? 'text-red-600' : 'text-slate-700'
      )}>
        {c.description}
        {res?.detail && (
          <span className="text-slate-400 ml-1">— {res.detail}</span>
        )}
      </span>
    </div>
  )

  // After
  return (
    <div key={c.criteria_id} className={cn(
      'pl-3 border-l-2 text-sm',
      res === undefined && 'border-slate-200 dark:border-zinc-700',
      passed === true  && 'border-emerald-300/60',
      passed === false && 'border-rose-300/50',
    )}>
      <span className={cn(
        res === undefined && 'text-slate-400 dark:text-slate-500',
        passed === true   && 'text-slate-700 dark:text-slate-300',
        passed === false  && 'text-slate-400 dark:text-slate-500',
      )}>
        {c.description}
        {res?.detail && (
          <span className="text-slate-400 ml-1">— {res.detail}</span>
        )}
      </span>
    </div>
  )
  ```

- [ ] In `frontend/src/steps/Step1Import.tsx`, add `FileUp` import from lucide-react:
  ```tsx
  import { FileUp } from 'lucide-react'
  ```

- [ ] In `frontend/src/steps/Step1Import.tsx`, replace the drop zone div's className and its emoji child:
  ```tsx
  // Before
  className="border-2 border-dashed border-slate-300 rounded-lg p-8 text-center text-slate-400 hover:border-slate-400 transition-colors cursor-pointer"
  ...
  <div className="text-4xl mb-2">📄</div>

  // After
  className="border-2 border-dashed border-slate-300 rounded-xl py-10 px-8 text-center text-slate-400 hover:border-slate-400 transition-colors cursor-pointer"
  ...
  <FileUp className="w-8 h-8 text-slate-300 mx-auto mb-3" strokeWidth={1.5} />
  ```

- [ ] Verify: run dev server. On Step1, drop zone shows `FileUp` icon (not emoji), has rounded-xl corners. On Step3, criteria items show left-border accent with no emoji prefix; passed items have emerald border, failed items have rose border, unevaluated items have slate border.
  ```bash
  cd frontend && npm run dev
  ```

- [ ] Commit
  ```bash
  git add frontend/src/steps/Step3Result.tsx frontend/src/steps/Step1Import.tsx
  git commit -m "feat(ui): Step3 left-border criteria, Step1 FileUp icon + rounded-xl drop zone"
  ```

---

## Self-Review Checklist

### Spec Coverage

| Spec Section | Task | Status |
|---|---|---|
| 1.2 Light token (`--background: 0 0% 97.5%`) | Task 1 | Covered |
| 1.3 Dark token (`.dark` block) | Task 1 | Covered |
| 1.4 useTheme hook (localStorage + prefers-color-scheme) | Task 2 | Covered |
| 1.5 ThemeToggle in header (flex-1 spacer fix) | Task 3 | Covered |
| Section 2 Geist font install + import + font-family | Task 1 | Covered |
| Section 3 rounded-xl large containers | Tasks 4, 5 | Covered |
| 4.1 Step2 dot+text badge (no background pill) | Task 4 | Covered |
| 4.2 EventLog borderless + responsive height + no mono | Task 4 | Covered |
| 4.3 Step2 failure panel `bg-rose-50/60` no border | Task 4 | Covered |
| 4.4 StageProgress text-xs + gap-2 + slate-300 done | Task 4 | Covered |
| 4.5 Step3 left-border criteria | Task 5 | Covered |
| 4.6 Step1 FileUp icon + rounded-xl | Task 5 | Covered |
| 4.7 `key={step}` + animate-in fade-in | Task 3 | Covered |

### No Placeholders

All code blocks are complete. No TBD, TODO, or placeholder values used.

### Type Consistency

- `useTheme()` returns `{ theme: Theme, toggleTheme: () => void }` — consistent between `useTheme.ts`, `ThemeToggle.tsx`, and test file.
- `Theme = 'light' | 'dark'` — named export used in hook, consumed in toggle component.
- `applyTheme(theme: Theme): void` — internal function, not exported, used only in `useTheme.ts`.
- `getInitialTheme(): Theme` — internal function, not exported, used only in `useTheme.ts`.
- `FileUp` — imported from `lucide-react` in `Step1Import.tsx` only; no cross-file dependency.
