// 后端 API 封装。开发环境通过 vite proxy 把 /api 转发到 http://127.0.0.1:8000。

async function request(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    throw new Error(`请求失败（HTTP ${res.status}）`)
  }
  return res.json()
}

// 诊断（多轮）
export function diagnose(payload) {
  return request('POST', '/api/diagnose', payload)
}

// 个人家电名单
export const listAppliances = () => request('GET', '/api/appliances')
export const createAppliance = (data) => request('POST', '/api/appliances', data)
export const deleteAppliance = (id) => request('DELETE', `/api/appliances/${id}`)

// 维修历史
export const listHistory = () => request('GET', '/api/history')
export const createHistory = (data) => request('POST', '/api/history', data)
export const deleteHistory = (id) => request('DELETE', `/api/history/${id}`)
