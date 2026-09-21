import { useState } from 'react'

const EMPTY_FORM = { brand: '海尔', model: '', category: '冰箱', date: '' }
const CATEGORY_EN = { 冰箱: 'refrigerator', 空调: 'air_conditioner' }

export default function ApplianceList({ appliances, selectedId, onSelect, onAdd, onDelete }) {
  const [showForm, setShowForm] = useState(false)
  const [openId, setOpenId] = useState(null)
  const [form, setForm] = useState(EMPTY_FORM)

  const submit = () => {
    onAdd({
      brand: form.brand,
      model: form.model.trim() || '未填型号',
      category: form.category,
      category_en: CATEGORY_EN[form.category] || 'refrigerator',
      date: form.date || '未填',
      warranty: form.date ? `保修至 ${form.date.slice(0, 4)}-待定` : '待定',
    })
    setShowForm(false)
    setForm(EMPTY_FORM)
  }

  const remove = (a) => {
    if (window.confirm(`确定删除「${a.brand} ${a.model}」吗？`)) onDelete(a.id)
  }

  return (
    <section className="rounded-card border border-line bg-panel p-4">
      <h2 className="mb-3 flex items-center gap-2 text-[13px] font-bold">
        <span className="h-3.5 w-1 rounded bg-brand"></span>
        我的家电
        <button
          onClick={() => setShowForm(true)}
          className="ml-auto rounded-full border border-brand px-3 py-0.5 text-xs font-semibold text-brand-deep transition-colors hover:bg-brand hover:text-white"
        >
          + 加入家电
        </button>
      </h2>
      <p className="mb-2 text-[11px] text-ink-soft">点击家电即可选中为当前诊断对象</p>

      <div className="space-y-2.5">
        {appliances.length === 0 && (
          <p className="py-4 text-center text-xs text-ink-soft">还没有家电，点右上角加入。</p>
        )}
        {appliances.map((a) => {
          const isSelected = selectedId === a.id
          return (
            <div
              key={a.id}
              className={`rounded-[10px] border bg-brand-soft ${
                isSelected ? 'border-brand ring-1 ring-brand' : 'border-line'
              }`}
            >
              <div className="flex items-center gap-2 px-3 py-2.5">
                <button
                  className="flex-1 text-left text-sm font-semibold hover:text-brand-deep"
                  onClick={() => onSelect(a.id)}
                >
                  {isSelected && <span className="mr-1 text-brand">●</span>}
                  {a.brand} {a.model}
                </button>
                <span className="whitespace-nowrap rounded-full bg-mist px-2 py-0.5 text-[11px] text-brand-deep">
                  {a.warranty}
                </span>
                <button
                  onClick={() => setOpenId(openId === a.id ? null : a.id)}
                  className="text-xs text-ink-soft"
                  title="展开详情"
                >
                  {openId === a.id ? '▴' : '▾'}
                </button>
                <button
                  onClick={() => remove(a)}
                  className="text-xs text-ink-soft transition-colors hover:text-safe-red"
                  title="删除"
                >
                  ✕
                </button>
              </div>
              {openId === a.id && (
                <div className="border-t border-dashed border-line px-3 py-2.5 text-xs text-ink-soft">
                  <div className="flex justify-between py-0.5">
                    <b className="font-semibold text-ink">品类</b>
                    <span>{a.category}</span>
                  </div>
                  <div className="flex justify-between py-0.5">
                    <b className="font-semibold text-ink">购买日期</b>
                    <span>{a.date}</span>
                  </div>
                  <div className="flex justify-between py-0.5">
                    <b className="font-semibold text-ink">保修</b>
                    <span>{a.warranty}</span>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {showForm && (
        <div className="fixed inset-0 z-50 grid place-items-center bg-ink/35">
          <div className="w-[400px] max-w-[90vw] rounded-card bg-panel p-5">
            <h3 className="mb-4 text-base font-bold">加入家电</h3>
            <label className="mt-2.5 block text-xs text-ink-soft">品牌</label>
            <select
              value={form.brand}
              onChange={(e) => setForm({ ...form, brand: e.target.value })}
              className="w-full rounded-lg border border-line px-3 py-2 text-sm"
            >
              <option>海尔</option>
              <option>美的</option>
              <option>西门子</option>
            </select>
            <label className="mt-2.5 block text-xs text-ink-soft">型号</label>
            <input
              value={form.model}
              onChange={(e) => setForm({ ...form, model: e.target.value })}
              placeholder="如 BCD-470WDPG"
              className="w-full rounded-lg border border-line px-3 py-2 text-sm outline-none focus:border-brand"
            />
            <label className="mt-2.5 block text-xs text-ink-soft">品类</label>
            <select
              value={form.category}
              onChange={(e) => setForm({ ...form, category: e.target.value })}
              className="w-full rounded-lg border border-line px-3 py-2 text-sm"
            >
              <option>冰箱</option>
              <option>空调</option>
            </select>
            <label className="mt-2.5 block text-xs text-ink-soft">购买日期</label>
            <input
              type="date"
              value={form.date}
              onChange={(e) => setForm({ ...form, date: e.target.value })}
              className="w-full rounded-lg border border-line px-3 py-2 text-sm outline-none focus:border-brand"
            />
            <div className="mt-5 flex gap-2.5">
              <button
                onClick={() => setShowForm(false)}
                className="flex-1 rounded-[10px] border border-line bg-brand-soft py-2 text-sm font-semibold text-ink"
              >
                取消
              </button>
              <button
                onClick={submit}
                className="flex-1 rounded-[10px] bg-brand py-2 text-sm font-semibold text-white hover:bg-brand-deep"
              >
                加入
              </button>
            </div>
          </div>
        </div>
      )}
    </section>
  )
}
