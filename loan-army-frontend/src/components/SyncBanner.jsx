import { useState, useEffect, useRef } from 'react'
import { RefreshCw, X } from 'lucide-react'

const DISMISS_KEY = 'sync_banner_dismissed'
const POLL_INTERVAL = 60_000

export default function SyncBanner() {
  const [syncing, setSyncing] = useState(false)
  const [message, setMessage] = useState('')
  const [dismissed, setDismissed] = useState(
    () => sessionStorage.getItem(DISMISS_KEY) === '1',
  )
  const timerRef = useRef(null)

  useEffect(() => {
    const fetchStatus = async () => {
      try {
        const res = await fetch('/api/sync-status')
        if (res.ok) {
          const data = await res.json()
          setSyncing(data.syncing)
          setMessage(data.message || '')
          if (!data.syncing) {
            sessionStorage.removeItem(DISMISS_KEY)
            setDismissed(false)
          }
        }
      } catch {
        // Silently ignore — banner just won't show
      }
    }

    fetchStatus()
    timerRef.current = setInterval(fetchStatus, POLL_INTERVAL)
    return () => clearInterval(timerRef.current)
  }, [])

  if (!syncing || dismissed) return null

  return (
    <div className="bg-amber-50 border-b border-amber-200 px-4 py-3">
      <div className="max-w-6xl mx-auto flex items-center justify-between gap-3 text-sm text-amber-800">
        <div className="flex items-center gap-2">
          <RefreshCw className="h-4 w-4 animate-spin flex-shrink-0" />
          <span>{message}</span>
        </div>
        <button
          onClick={() => {
            sessionStorage.setItem(DISMISS_KEY, '1')
            setDismissed(true)
          }}
          className="flex-shrink-0 p-1 rounded hover:bg-amber-100 transition-colors"
          aria-label="Dismiss banner"
        >
          <X className="h-4 w-4" />
        </button>
      </div>
    </div>
  )
}
