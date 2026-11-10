import { useEffect, useState } from 'react'
import { checkHealth } from '../api/health.ts'

type Status = 'checking' | 'online' | 'offline'

const LABELS: Record<Status, string> = {
  checking: 'Checking the API…',
  online: 'API online',
  offline: 'API offline',
}

// Small, beside the app's name: a coloured dot, and the text that says the same for anyone who can't see the colour.
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

  return (
    <p className="api-status" role="status">
      <span className={`status-dot ${status}`} aria-hidden="true" />
      {LABELS[status]}
    </p>
  )
}
