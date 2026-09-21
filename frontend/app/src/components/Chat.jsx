import { useEffect, useRef, useState } from 'react'
import { diagnose } from '../api'

const LEVEL = {
  green: { text: '可安全自修', badge: '绿 · 可安全自修', lamp: 'bg-safe-green' },
  yellow: { text: '谨慎操作 · 需断电', badge: '黄 · 谨慎操作', lamp: 'bg-safe-yellow' },
  red: { text: '必须联系专业师傅', badge: '红 · 必须找师傅', lamp: 'bg-safe-red' },
}

// 完整静态类名（Tailwind 无法识别动态拼接的类名）
const BADGE = {
  green: 'bg-safe-green-bg text-safe-green',
  yellow: 'bg-safe-yellow-bg text-safe-yellow',
  red: 'bg-safe-red-bg text-safe-red',
}

// 把 FileReader 的 dataUrl 拆成 media_type 和纯 base64（后端要的是不含前缀的 base64）
function parseDataUrl(dataUrl) {
  const m = dataUrl.match(/^data:([^;]+);base64,(.+)$/)
  return m ? { media_type: m[1], base64: m[2] } : null
}

export default function Chat({ appliances, selected, onSelect, onDiagnosed }) {
  const [messages, setMessages] = useState([
    { type: 'agent', text: '你好，我是家电医生。先在左侧选中要诊断的家电，然后描述问题。' },
  ])
  const [threadId, setThreadId] = useState(null)
  const [input, setInput] = useState('')
  const [img, setImg] = useState(null)
  const [busy, setBusy] = useState(false)
  const bodyRef = useRef(null)

  // 切换诊断对象时，作废上一轮多轮会话
  useEffect(() => {
    setThreadId(null)
  }, [selected?.id])

  const scroll = () => {
    const el = bodyRef.current
    if (el) el.scrollTop = el.scrollHeight
  }
  const push = (m) => {
    setMessages((prev) => [...prev, m])
    setTimeout(scroll, 0)
  }

  function handleResponse(r) {
    if (r.status === 'need_info') {
      setThreadId(r.thread_id)
      push({ type: 'agent', text: r.question })
    } else if (r.status === 'done') {
      setThreadId(null)
      const report = {
        brand: selected.brand,
        model: selected.model,
        category: selected.category,
        diagnosis: r.diagnosis || '',
        safety_level: r.safety_level || 'yellow',
        safety_check: r.safety_check,
        hypotheses: r.hypotheses || [],
      }
      push({ type: 'report', report })
      onDiagnosed({
        id: Date.now(),
        brand: `${report.brand}${report.category}`,
        model: report.model,
        level: report.safety_level,
        issue: LEVEL[report.safety_level]?.text || report.safety_level,
        date: '刚刚',
        detail: report.diagnosis || report.hypotheses.join('；') || '（未给出结论）',
      })
    }
  }

  async function send() {
    const v = input.trim()
    if ((!v && !img) || busy) return
    setInput('')
    const imgDataUrl = img
    setImg(null)
    push({ type: 'user', text: v || '（仅图片）', img: imgDataUrl })

    if (!selected) {
      // 未选家电：询问是哪台
      push({ type: 'agent', text: '先确认一下：你要诊断的是哪台家电？' })
      push({ type: 'question', text: '请选择要诊断的家电：', options: appliances.map((a) => ({ label: `${a.brand} ${a.model}`, applianceId: a.id })), answered: false })
      return
    }

    // 拆图片为 media_type + base64（仅首次提问携带）
    const imgFields = {}
    if (imgDataUrl) {
      const p = parseDataUrl(imgDataUrl)
      if (p) {
        imgFields.image_base64 = p.base64
        imgFields.media_type = p.media_type
      }
    }

    setBusy(true)
    try {
      let r
      if (threadId) {
        // 回答上一轮追问
        r = await diagnose({ thread_id: threadId, answer: v })
      } else {
        // 首次提问
        r = await diagnose({
          brand: selected.brand,
          category: selected.category_en || 'refrigerator',
          model: selected.model,
          symptom: v,
          ...imgFields,
        })
      }
      handleResponse(r)
    } catch (e) {
      push({ type: 'agent', text: `请求失败：${e.message}。请确认后端服务已启动（uvicorn + Milvus + .env 配好 DeepSeek key）。` })
    } finally {
      setBusy(false)
    }
  }

  function answerAppliance(idx, opt) {
    setMessages((prev) => prev.map((m, i) => (i === idx ? { ...m, answered: true } : m)))
    push({ type: 'user', text: opt.label })
    onSelect(opt.applianceId)
    const a = appliances.find((x) => x.id === opt.applianceId)
    push({ type: 'agent', text: `已选择「${a.brand} ${a.model}」。请描述遇到的问题。` })
  }

  const onPickImage = (e) => {
    const f = e.target.files?.[0]
    if (!f) return
    const reader = new FileReader()
    reader.onload = () => setImg(reader.result)
    reader.readAsDataURL(f)
    e.target.value = ''
  }

  return (
    <section className="flex min-h-[560px] flex-1 flex-col rounded-card border border-line bg-panel">
      <div className="border-b border-line px-5 py-3.5 text-sm font-bold">
        提问诊断
        <span className="ml-2 text-xs font-normal text-ink-soft">文字或照片描述你的冰箱问题</span>
      </div>

      {/* 当前诊断对象 */}
      <div className="border-b border-line bg-brand-soft px-5 py-2 text-xs">
        {selected ? (
          <span>
            正在诊断：<b className="text-brand-deep">{selected.brand} {selected.model}</b>
            <span className="ml-2 text-ink-soft">（{selected.category} · {selected.warranty}）</span>
          </span>
        ) : (
          <span className="text-ink-soft">尚未选择家电 —— 提问时我会先询问，或到左侧「我的家电」点击选中。</span>
        )}
      </div>

      <div ref={bodyRef} className="flex flex-1 flex-col gap-3.5 overflow-y-auto px-5 py-5">
        {messages.map((m, i) => {
          if (m.type === 'user') {
            return (
              <div key={i} className="max-w-[78%] self-end rounded-xl rounded-br-sm bg-brand px-4 py-2.5 text-sm text-white">
                {m.text}
                {m.img && <img src={m.img} alt="上传" className="mt-2 max-w-[180px] rounded-lg" />}
              </div>
            )
          }
          if (m.type === 'agent') {
            return (
              <div key={i} className="max-w-[78%] self-start rounded-xl rounded-bl-sm border border-line bg-brand-soft px-4 py-2.5 text-sm">
                {m.text}
              </div>
            )
          }
          if (m.type === 'question') {
            return (
              <div key={i} className="max-w-[78%] self-start">
                <div className="rounded-xl rounded-bl-sm border border-line bg-brand-soft px-4 py-2.5 text-sm">{m.text}</div>
                <div className="mt-2 flex flex-wrap gap-2">
                  {m.options.map((opt, oi) => (
                    <button
                      key={oi}
                      disabled={m.answered}
                      onClick={() => answerAppliance(i, opt)}
                      className="rounded-full border border-brand px-3.5 py-1.5 text-[13px] text-brand-deep transition-colors hover:bg-brand hover:text-white disabled:cursor-not-allowed disabled:opacity-40"
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              </div>
            )
          }
          if (m.type === 'report') {
            const r = m.report
            const L = LEVEL[r.safety_level] || { text: r.safety_level, badge: r.safety_level, lamp: 'bg-line' }
            const badgeCls = BADGE[r.safety_level] || 'bg-brand-soft text-ink-soft'
            return (
              <div key={i} className="w-full max-w-[92%] self-start overflow-hidden rounded-card border border-line">
                <div className="flex items-center gap-3 border-b border-line bg-brand-soft px-4 py-3.5">
                  <div className="text-[11px] uppercase tracking-wider text-ink-soft">
                    诊断报告
                    <b className="mt-0.5 block text-[15px] font-bold tracking-normal text-ink">
                      {r.brand} {r.model} · {r.category}
                    </b>
                  </div>
                  <div className="ml-auto flex items-center gap-1.5 text-xs font-semibold">
                    <span className={`h-3 w-3 rounded-full shadow ${L.lamp}`}></span>
                    {L.text}
                  </div>
                </div>
                <div className="flex items-start gap-2.5 px-4 py-3.5 text-[13px]">
                  <span className={`shrink-0 rounded-full px-3 py-0.5 text-xs font-bold ${badgeCls}`}>
                    {L.badge}
                  </span>
                  <span>{r.diagnosis || (r.hypotheses.length > 0 ? '下面给出可能的原因' : '（未给出诊断结论）')}</span>
                </div>
                {(r.hypotheses.length > 0 || r.safety_check) && (
                  <div className="px-4 pb-4 text-sm">
                    {r.hypotheses.length > 0 && (
                      <>
                        <h4 className="mb-1.5 text-xs font-semibold text-ink-soft">可能原因</h4>
                        <ul className="list-disc pl-5">
                          {r.hypotheses.map((h, hi) => (
                            <li key={hi} className="mb-1">{h}</li>
                          ))}
                        </ul>
                      </>
                    )}
                    {r.safety_check && (
                      <>
                        <h4 className="mb-1.5 mt-3 text-xs font-semibold text-ink-soft">安全审查</h4>
                        <p className="text-[13px] text-safe-red">{r.safety_check}</p>
                      </>
                    )}
                  </div>
                )}
              </div>
            )
          }
          return null
        })}
      </div>

      <div className="flex items-center gap-2.5 border-t border-line px-5 py-3.5">
        <label className="relative grid h-10 w-10 shrink-0 cursor-pointer place-items-center rounded-[10px] border border-line bg-brand-soft text-ink-soft transition-colors hover:border-brand hover:text-brand-deep">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <rect x="3" y="3" width="18" height="18" rx="2" />
            <circle cx="8.5" cy="8.5" r="1.5" />
            <path d="M21 15l-5-5L5 21" />
          </svg>
          <input type="file" accept="image/*" onChange={onPickImage} className="absolute inset-0 cursor-pointer opacity-0" />
        </label>
        {img && (
          <div className="flex items-center gap-2">
            <img src={img} alt="预览" className="h-10 w-10 rounded-lg border border-line object-cover" />
            <button onClick={() => setImg(null)} className="text-xs text-safe-red">✕</button>
          </div>
        )}
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && send()}
          placeholder={threadId ? '请回答上面的问题…' : '描述症状（如：压缩机嗡嗡几秒就停，反复循环）'}
          className="flex-1 rounded-[10px] border border-line bg-brand-soft px-4 py-2.5 text-sm outline-none focus:border-brand"
        />
        <button
          onClick={send}
          disabled={busy}
          className="rounded-[10px] bg-brand px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-brand-deep disabled:opacity-50"
        >
          {busy ? '诊断中…' : '发送'}
        </button>
      </div>
    </section>
  )
}
