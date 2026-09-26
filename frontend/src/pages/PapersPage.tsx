// frontend/src/pages/PapersPage.tsx
// 论文库视图：Phase 2 的占位页。先把信息架构立住——上传与解析状态、
// 全文与知识浏览、从论文直接发起任务；数据层（PDF / MinerU 全文 / 知识 JSON）
// 已在服务端就绪，本页上线时只差列表与预览端点。
import { FileText, LibraryBig, Play, ScanSearch } from 'lucide-react'

const FEATURES = [
  {
    icon: ScanSearch,
    title: '解析与状态',
    desc: 'MinerU 全文解析，进度与失败重试一目了然。',
  },
  {
    icon: FileText,
    title: '全文与知识',
    desc: '直接阅读解析后的论文，公式 / 参数 / 验收标准随手查。',
  },
  {
    icon: Play,
    title: '一键复用',
    desc: '知识已抽好的论文直接发起新一轮仿真，不必重复解析与抽取。',
  },
]

export function PapersPage() {
  return (
    <div className="max-w-2xl mx-auto text-center py-10 lg:py-16">
      <div className="mx-auto w-14 h-14 rounded-2xl bg-blue-600/10 flex items-center justify-center">
        <LibraryBig className="w-7 h-7 text-blue-600 dark:text-blue-400" />
      </div>
      <h1 className="mt-5 text-2xl font-semibold tracking-tight text-foreground">论文库</h1>
      <p className="mt-2 text-sm leading-relaxed text-muted-foreground max-w-[52ch] mx-auto">
        传过的论文都在这里复用：解析全文、抽取出的知识与验收标准、每一次仿真任务，按论文归档浏览。
      </p>

      <div className="mt-8 grid gap-3 text-left sm:grid-cols-3">
        {FEATURES.map(f => (
          <div key={f.title} className="rounded-xl border border-border bg-card p-4">
            <f.icon className="w-4 h-4 text-blue-600 dark:text-blue-400" />
            <h2 className="mt-2.5 text-[13px] font-semibold text-foreground">{f.title}</h2>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">{f.desc}</p>
          </div>
        ))}
      </div>

      <p className="mt-8 inline-flex items-center gap-1.5 text-[11px] px-2.5 py-1 rounded-full border border-border bg-muted/40 text-muted-foreground">
        <span className="w-1.5 h-1.5 rounded-full bg-blue-500" />
        下一阶段上线 · 数据层已就绪
      </p>
    </div>
  )
}
