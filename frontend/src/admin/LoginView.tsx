import { useState } from 'react'
import { adminApi } from './api'

export function LoginView({ onLogin }: { onLogin: (username: string) => void }) {
  const [username, setUsername] = useState('admin')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')

  return (
    <main className="admin-login">
      <form onSubmit={async (event) => {
        event.preventDefault()
        setError('')
        try { onLogin((await adminApi.login(username, password)).username) }
        catch (reason) { setError(reason instanceof Error ? reason.message : '登录失败') }
      }}>
        <div className="admin-login-mark">DML</div>
        <h1>问卷管理后台</h1>
        <p>查看反馈并维护角色、页面与功能目录。</p>
        <label><span>管理员账号</span><input autoComplete="username" value={username} onChange={(event) => setUsername(event.target.value)} /></label>
        <label><span>密码</span><input type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} /></label>
        {error ? <div className="admin-error">{error}</div> : null}
        <button className="admin-primary">登录</button>
      </form>
    </main>
  )
}
