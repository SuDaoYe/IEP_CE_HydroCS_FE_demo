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
    <div className="min-h-screen flex items-center justify-center bg-[#0a0e17]">
      <Card className="w-full max-w-sm bg-[#131820] border border-[#1e2430]">
        <CardHeader className="flex-col gap-1 pt-8 pb-0">
          <h1 className="text-xl font-semibold text-[#c8ccd0]">HYDRO·CS</h1>
          <p className="text-sm text-[#6b7280]">智能灌溉管理平台</p>
        </CardHeader>
        <CardBody className="gap-4 pt-6 pb-8 px-8">
          <form onSubmit={handleSubmit} className="flex flex-col gap-4">
            <Input
              label="用户名"
              value={username}
              onValueChange={setUsername}
              variant="bordered"
              classNames={{ input: 'text-[#c8ccd0]', label: 'text-[#6b7280]' }}
            />
            <Input
              label="密码"
              type="password"
              value={password}
              onValueChange={setPassword}
              variant="bordered"
              classNames={{ input: 'text-[#c8ccd0]', label: 'text-[#6b7280]' }}
            />
            {error && <p className="text-red-400 text-xs">{error}</p>}
            <Button type="submit" isLoading={loading} className="bg-[#818cf8] text-white mt-2">
              登录
            </Button>
          </form>
          <p className="text-[10px] text-[#6b7280] text-center mt-2">
            测试账号: admin/admin123 | farmer1/123456 | farmer2/123456
          </p>
        </CardBody>
      </Card>
    </div>
  )
}
