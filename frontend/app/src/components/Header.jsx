export default function Header() {
  return (
    <header className="flex items-center gap-3.5 border-b border-line bg-panel px-7 py-3.5">
      <div className="grid h-9 w-9 place-items-center rounded-lg bg-brand text-lg font-bold text-white">
        诊
      </div>
      <div>
        <div className="text-[17px] font-bold tracking-wide">家电医生</div>
        <div className="text-xs text-ink-soft">冰箱故障诊断 · 三级安全护栏</div>
      </div>
      <div className="ml-auto rounded-full border border-line bg-brand-soft px-3 py-1 text-xs text-ink-soft">
        演示版 · 数据为模拟
      </div>
    </header>
  )
}
