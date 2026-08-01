import { useState, type FormEvent } from "react"
import { authenticateWorkbench } from "@/api/workbench"

export function SignInPanel({ onSignedIn }: { onSignedIn: () => void }) {
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      await authenticateWorkbench(email, password)
      onSignedIn()
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "登录失败")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="signin-page">
      <form className="signin-panel" onSubmit={submit}>
        <p className="section-eyebrow">受保护的工作台</p>
        <h1>登录</h1>
        <label>
          <span>邮箱</span>
          <input
            autoComplete="email"
            onChange={(event) => setEmail(event.target.value)}
            required
            type="email"
            value={email}
          />
        </label>
        <label>
          <span>密码</span>
          <input
            autoComplete="current-password"
            onChange={(event) => setPassword(event.target.value)}
            required
            type="password"
            value={password}
          />
        </label>
        {error ? <p className="signin-error" role="alert">{error}</p> : null}
        <button className="primary-button" disabled={submitting} type="submit">
          {submitting ? "正在登录" : "登录工作台"}
        </button>
      </form>
    </main>
  )
}
