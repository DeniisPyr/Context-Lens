import { useEffect, useState } from 'react'
import { checkHealth } from './api/health.ts'

type ApiStatus = 'checking' | 'online' | 'offline'

export default function App() {
  const [apiStatus, setApiStatus] = useState<ApiStatus>('checking')

  useEffect(() => {
    const controller = new AbortController()
    checkHealth(controller.signal)
      .then((healthy) => setApiStatus(healthy ? 'online' : 'offline'))
      .catch(() => {
        if (!controller.signal.aborted) setApiStatus('offline')
      })
    return () => controller.abort()
  }, [])

  return (
    <main>
      <h1>Context-Lens</h1>
      <p>Ask questions about your documents and get answers you can check.</p>
      <p role="status">API: {apiStatus}</p>
    </main>
  )
}
