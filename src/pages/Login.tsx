import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Input, Button, Card, CardBody, CardHeader } from '@heroui/react'
import { useAuth } from '../store/AuthContext'

export default function Login() {
  const { login, user } = useAuth()
  const navigate = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  if (user) {
    navigate(user.role === 'admin' ? '/admin' : '/dashboard', { replace: true })
    return null
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setLoading(true)
    try {
      await login(username, password)
      navigate(username === 'admin' ? '/admin' : '/dashboard', { replace: true })
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--bg-page)]">
      <Card className="w-full max-w-sm bg-[var(--bg-panel)] border border-[var(--border)]">
        <CardHeader className="flex-col gap-1 pt-8 pb-0">
          <h1 className="text-xl font-semibold text-[var(--text-primary)]">HYDRO·CS</h1>
          <p className="text-sm text-[var(--text-muted)]">智能灌溉管理平台</p>
        </CardHeader>
        <CardBody className="gap-4 pt-6 pb-8 px-8">
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <Input
              placeholder="用户名"
              value={username}
              onValueChange={setUsername}
              variant="bordered"
              classNames={{ input: 'text-[var(--text-primary)] placeholder:text-[var(--text-muted)]' }}
            />
            <Input
              placeholder="密码"
              type="password"
              value={password}
              onValueChange={setPassword}
              variant="bordered"
              classNames={{ input: 'text-[var(--text-primary)] placeholder:text-[var(--text-muted)]' }}
            />
            {error && <p className="text-red-400 text-xs">{error}</p>}
            <Button type="submit" isLoading={loading} className="bg-[var(--accent)] text-white mt-2">
              登录
            </Button>
          </form>
          <p className="text-[10px] text-[var(--text-muted)] text-center mt-2">
            测试账号: admin/admin123 | farmer1/123456 | farmer2/123456
          </p>
        </CardBody>
      </Card>
    </div>
  )
}
