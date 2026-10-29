export function fmtNumber(value: number | null | undefined, digits = 1): string {
  if (value === null || value === undefined || Number.isNaN(value)) return '—'
  return value.toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}

export function fmtMu(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  if (value === 0) return '0 亩'
  if (value < 1) return `${fmtNumber(value * 100, 0)} 厘`
  return `${fmtNumber(value, value < 10 ? 2 : 1)} 亩`
}

export function fmtM3(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  if (value >= 1000) return `${fmtNumber(value / 1000, 2)} 千m³`
  return `${fmtNumber(value, value < 10 ? 2 : 1)} m³`
}

export function fmtMm(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—'
  return `${fmtNumber(value, 2)} mm`
}

export function fmtDate(iso: string): string {
  const date = new Date(iso.length <= 10 ? `${iso}T00:00:00` : iso)
  return `${date.getMonth() + 1}月${date.getDate()}日`
}

export function fmtWeekday(iso: string): string {
  const date = new Date(iso.length <= 10 ? `${iso}T00:00:00` : iso)
  return ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][date.getDay()]
}

export function fmtDateTime(iso: string): string {
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return iso
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${date.getMonth() + 1}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
}

export function relativeTime(iso: string): string {
  const then = new Date(iso).getTime()
  if (Number.isNaN(then)) return iso
  const diff = Date.now() - then
  const minutes = Math.round(diff / 60000)
  if (minutes < 1) return '刚刚'
  if (minutes < 60) return `${minutes} 分钟前`
  const hours = Math.round(minutes / 60)
  if (hours < 24) return `${hours} 小时前`
  const days = Math.round(hours / 24)
  if (days < 30) return `${days} 天前`
  return fmtDate(iso)
}

export function clamp(value: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, value))
}
