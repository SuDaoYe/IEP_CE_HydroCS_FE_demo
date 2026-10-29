import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../store/auth'
import { Icon, Spinner } from '../components/ui'

const ACCOUNTS = [
  { username: 'farmer1', password: '123456', name: '王建国', role: '农户' },
  { username: 'farmer2', password: '123456', name: '李秀兰', role: '农户' },
  { username: 'admin', password: 'admin123', name: '管理员', role: '管理员' },
]

export default function Login() {
  const navigate = useNavigate()
  const login = useAuth((state) => state.login)
  const user = useAuth((state) => state.user)
  const loading = useAuth((state) => state.loading)
  const error = useAuth((state) => state.error)

  const [username, setUsername] = useState('farmer1')
  const [password, setPassword] = useState('123456')

  useEffect(() => {
    if (user) navigate(user.role === 'admin' ? '/admin' : '/', { replace: true })
  }, [user, navigate])

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    try {
      await login(username.trim(), password)
      navigate(username.trim() === 'admin' ? '/admin' : '/', { replace: true })
    } catch {
      /* error surfaced through the store */
    }
  }

  return (
    <div className="relative flex min-h-dvh flex-col bg-[var(--hc-canvas)] lg:flex-row">
      {/* brand side */}
      <div className="relative hidden flex-1 overflow-hidden border-r border-[var(--hc-line)] lg:block">
        <div
          className="absolute inset-0 opacity-[0.5]"
          style={{
            background:
              'radial-gradient(120% 90% at 15% 10%, rgba(53,211,153,0.16), transparent 55%), radial-gradient(90% 70% at 85% 85%, rgba(74,168,240,0.14), transparent 60%)',
          }}
        />
        <svg className="absolute inset-0 h-full w-full opacity-[0.16]" aria-hidden="true">
          <defs>
            <pattern id="grid" width="46" height="46" patternUnits="userSpaceOnUse">
              <path d="M46 0H0V46" fill="none" stroke="#93a2b1" strokeWidth="0.6" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill="url(#grid)" />
        </svg>

        <div className="relative flex h-full flex-col justify-between p-10">
          <div className="flex items-center gap-2.5">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-[var(--hc-accent)]/14 text-[var(--hc-accent)]">
              <Icon name="water" size={19} />
            </div>
            <span className="text-[13px] font-semibold tracking-[0.22em] text-[var(--hc-ink)]">HYDRO·CS</span>
          </div>

          <div className="max-w-[440px]">
            <h1 className="text-[34px] font-semibold leading-[1.22] tracking-tight text-[var(--hc-ink)]">
              看清每一块地，
              <br />
              算出每一次该浇多少水。
            </h1>
            <p className="mt-4 text-[13px] leading-relaxed text-[var(--hc-muted)]">
              卫星影像自动识别田块边界 → 手工修正形状 → 按作物生育期与逐日蒸散量解算需水量。
              识别在服务端完成，田块与历史记录在手机上离线可查。
            </p>
            <div className="mt-6 flex flex-wrap gap-2">
              {['YOLO11s-seg 田块识别', 'ETMonitor 逐日蒸散网格', '离线优先 · 增量同步'].map((item) => (
                <span key={item} className="hc-chip border-[var(--hc-line-strong,#2a3a49)]">
                  {item}
                </span>
              ))}
            </div>
          </div>

          <div className="flex items-center gap-6 text-[10.5px] text-[var(--hc-faint)]">
            <span>华北大平原 · 0.25° 蒸散网格</span>
            <span>影像 Esri / 高德 / Sentinel-2</span>
          </div>
        </div>
      </div>

      {/* form side */}
      <div className="flex flex-1 items-center justify-center px-5 py-10">
        <div className="w-full max-w-[360px]">
          <div className="mb-7 flex items-center gap-2.5 lg:hidden">
            <div className="grid h-9 w-9 place-items-center rounded-xl bg-[var(--hc-accent)]/14 text-[var(--hc-accent)]">
              <Icon name="water" size={19} />
            </div>
            <div>
              <div className="text-[13px] font-semibold tracking-[0.2em] text-[var(--hc-ink)]">HYDRO·CS</div>
              <div className="text-[10px] text-[var(--hc-faint)]">智能灌溉管理</div>
            </div>
          </div>

          <h2 className="text-[19px] font-semibold text-[var(--hc-ink)]">登录</h2>
          <p className="mt-1 text-[12px] text-[var(--hc-faint)]">使用农户或管理员账号进入工作台</p>

          <form onSubmit={submit} className="mt-6 flex flex-col gap-3">
            <label className="flex flex-col gap-1.5">
              <span className="hc-label">用户名</span>
              <input
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                className="hc-input h-11"
                autoComplete="username"
                placeholder="farmer1"
              />
            </label>
            <label className="flex flex-col gap-1.5">
              <span className="hc-label">密码</span>
              <input
                type="password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                className="hc-input h-11"
                autoComplete="current-password"
                placeholder="••••••"
              />
            </label>
            {error && (
              <div className="rounded-lg border border-[var(--hc-danger)]/40 bg-[var(--hc-danger)]/8 px-3 py-2 text-[11.5px] text-[var(--hc-danger)]">
                {error}
              </div>
            )}
            <button type="submit" className="hc-btn hc-btn-primary mt-1 h-11" disabled={loading}>
              {loading ? <Spinner size={14} /> : <Icon name="check" size={15} />}
              登录
            </button>
          </form>

          <div className="mt-7">
            <div className="hc-label mb-2">演示账号 · 点击填入</div>
            <div className="flex flex-col gap-1.5">
              {ACCOUNTS.map((account) => (
                <button
                  key={account.username}
                  type="button"
                  onClick={() => {
                    setUsername(account.username)
                    setPassword(account.password)
                  }}
                  className="flex items-center gap-2 rounded-lg border border-[var(--hc-line)] bg-[var(--hc-surface)] px-2.5 py-2 text-left transition hover:border-[var(--hc-line-strong,#2a3a49)]"
                >
                  <span className="text-[12px] text-[var(--hc-ink)]">{account.name}</span>
                  <span className="hc-num text-[10.5px] text-[var(--hc-faint)]">
                    {account.username} / {account.password}
                  </span>
                  <span className="hc-chip ml-auto">{account.role}</span>
                </button>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
