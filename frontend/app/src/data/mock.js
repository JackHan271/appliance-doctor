// 模拟数据。正式接后端后，这里替换为对 /api 的请求。

export const initialAppliances = [
  { id: 1, brand: '海尔', model: 'BCD-470WDPG', category: '冰箱', category_en: 'refrigerator', date: '2024-03-15', warranty: '保修至 2027-03' },
  { id: 2, brand: '美的', model: 'BCD-550WKGPZM', category: '冰箱', category_en: 'refrigerator', date: '2025-01-10', warranty: '保修至 2028-01' },
  { id: 3, brand: '西门子', model: 'KA92NV02TI', category: '冰箱', category_en: 'refrigerator', date: '2022-06-01', warranty: '已过保' },
]

export const initialHistory = [
  { id: 1, brand: '海尔冰箱', model: 'BCD-470WDPG', level: 'red', issue: '传感器故障', date: '09-12', detail: 'E1 冷藏室传感器短路，已联系售后检修。' },
  { id: 2, brand: '美的冰箱', model: 'BCD-550WKGPZM', level: 'yellow', issue: '超温报警', date: '09-08', detail: 'E6 超温报警，自查门封后恢复正常。' },
  { id: 3, brand: '西门子冰箱', model: 'KA92NV02TI', level: 'green', issue: '门封清洁', date: '08-30', detail: '门封条清洁，冷气外漏已解决。' },
]
