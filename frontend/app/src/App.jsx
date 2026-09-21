import { useEffect, useState } from 'react'
import Header from './components/Header'
import ApplianceList from './components/ApplianceList'
import HistoryList from './components/HistoryList'
import SafetyManual from './components/SafetyManual'
import Chat from './components/Chat'
import {
  listAppliances,
  createAppliance,
  deleteAppliance,
  listHistory,
  createHistory,
  deleteHistory,
} from './api'

export default function App() {
  const [appliances, setAppliances] = useState([])
  const [history, setHistory] = useState([])
  const [selectedId, setSelectedId] = useState(null)

  // 启动时从后端拉取数据
  useEffect(() => {
    ;(async () => {
      try {
        const [a, h] = await Promise.all([listAppliances(), listHistory()])
        setAppliances(a)
        setHistory(h)
      } catch (e) {
        console.error('加载数据失败：', e)
      }
    })()
  }, [])

  const selected = appliances.find((a) => a.id === selectedId) || null

  const addAppliance = async (data) => {
    try {
      const a = await createAppliance(data)
      setAppliances((prev) => [...prev, a])
    } catch (e) {
      console.error('加入家电失败：', e)
    }
  }

  const removeAppliance = async (id) => {
    try {
      await deleteAppliance(id)
      setAppliances((prev) => prev.filter((x) => x.id !== id))
      if (selectedId === id) setSelectedId(null)
    } catch (e) {
      console.error('删除家电失败：', e)
    }
  }

  const removeHistory = async (id) => {
    try {
      await deleteHistory(id)
      setHistory((prev) => prev.filter((x) => x.id !== id))
    } catch (e) {
      console.error('删除历史失败：', e)
    }
  }

  const addHistory = async (data) => {
    try {
      const h = await createHistory(data)
      setHistory((prev) => [h, ...prev])
    } catch (e) {
      console.error('保存历史失败：', e)
    }
  }

  return (
    <div className="min-h-screen bg-mist text-ink">
      <Header />
      <main className="mx-auto flex max-w-[1280px] items-start gap-5 px-7 py-5">
        <aside className="flex w-80 shrink-0 flex-col gap-4">
          <ApplianceList
            appliances={appliances}
            selectedId={selectedId}
            onSelect={setSelectedId}
            onAdd={addAppliance}
            onDelete={removeAppliance}
          />
          <HistoryList history={history} onDelete={removeHistory} />
          <SafetyManual />
        </aside>
        <Chat
          appliances={appliances}
          selected={selected}
          onSelect={setSelectedId}
          onDiagnosed={addHistory}
        />
      </main>
    </div>
  )
}
