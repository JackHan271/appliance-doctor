const TIPS = [
  { title: '断电第一', text: '任何拆盖/清理内部前先拔电源插头。' },
  { title: '勿碰制冷剂', text: '涉及压缩机、管路、制冷剂，务必联系售后。' },
  { title: '勿用锐器除霜', text: '避免戳破内胆或蒸发器。' },
]

export default function SafetyManual() {
  return (
    <section className="rounded-card border border-line bg-panel p-4">
      <h2 className="mb-3 flex items-center gap-2 text-[13px] font-bold">
        <span className="h-3.5 w-1 rounded bg-brand"></span>
        通用安全手册
      </h2>
      {TIPS.map((t) => (
        <div key={t.title} className="border-b border-dashed border-line py-2 text-[13px] last:border-none">
          <b className="block text-xs text-safe-red">{t.title}</b>
          {t.text}
        </div>
      ))}
    </section>
  )
}
