import { useEffect, useState } from 'react'
import { checkHealth } from '../api/health.ts'

type Status = 'checking' | 'online' | 'offline'

export default function ApiStatus() {
  const [status, setStatus] = useState<Status>('checking')

  useEffect(() => {
    const controller = new AbortController()
    checkHealth(controller.signal)
      .then((healthy) => setStatus(healthy ? 'online' : 'offline'))
      .catch(() => {
        if (!controller.signal.aborted) setStatus('offline')
      })
    return () => controller.abort()
  }, [])

  return <p role="status">API: {status}</p>
}
