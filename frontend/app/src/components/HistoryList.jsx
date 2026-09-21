import { useState } from 'react'

const DOT = { green: 'bg-safe-green', yellow: 'bg-safe-yellow', red: 'bg-safe-red' }

export default function HistoryList({ history, onDelete }) {
  const [openId, setOpenId] = useState(null)

  const remove = (h) => {
    if (window.confirm(`确定删除这条维修记录（${h.issue}）吗？`)) onDelete(h.id)
  }

  return (
    <section className="rounded-card border border-line bg-panel p-4">
      <h2 className="mb-3 flex items-center gap-2 text-[13px] font-bold">
        <span className="h-3.5 w-1 rounded bg-brand"></span>
        维修历史
      </h2>
      <div className="space-y-2.5">
        {history.length === 0 && (
          <p className="py-4 text-center text-xs text-ink-soft">暂无维修记录。</p>
        )}
        {history.map((h) => (
          <div key={h.id} className="rounded-[10px] border border-line bg-brand-soft">
            <div className="flex items-center gap-2 px-3 py-2.5">
              <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${DOT[h.level] || 'bg-line'}`}></span>
              <button
                className="flex-1 text-left text-sm font-semibold hover:text-brand-deep"
                onClick={() => setOpenId(openId === h.id ? null : h.id)}
              >
                {h.brand}
                <span className="ml-1 text-xs text-ink-soft">{openId === h.id ? '▴' : '▾'}</span>
              </button>
              <span className="whitespace-nowrap rounded-full bg-mist px-2 py-0.5 text-[11px] text-brand-deep">
                {h.issue} · {h.date}
              </span>
              <button
                onClick={() => remove(h)}
                className="text-xs text-ink-soft transition-colors hover:text-safe-red"
                title="删除"
              >
                ✕
              </button>
            </div>
            {openId === h.id && (
              <div className="border-t border-dashed border-line px-3 py-2.5 text-xs text-ink-soft">
                <div className="flex justify-between py-0.5">
                  <b className="font-semibold text-ink">型号</b>
                  <span>{h.model}</span>
                </div>
                <div className="py-0.5">
                  <b className="font-semibold text-ink">结论</b>
                  <p className="mt-1">{h.detail}</p>
                </div>
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  )
}
