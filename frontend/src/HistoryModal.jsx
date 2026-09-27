import { useEffect, useState } from 'react'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'

import { apiFetch, checkedJson, sessionUrl } from './api.js'

export default function HistoryModal({ open, onOpenChange }) {
  const [cycles, setCycles] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!open) return
    setLoading(true)
    apiFetch('/history')
      .then(checkedJson)
      .then((data) => { setCycles(data.cycles || []); setError(null) })
      .catch(() => setError("Can't reach the backend to load history."))
      .finally(() => setLoading(false))
  }, [open])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[82vh] flex flex-col">
        <DialogHeader className="flex-row items-center justify-between space-y-0">
          <DialogTitle className="font-display">Cycle history</DialogTitle>
          <Button variant="outline" size="sm" className="mr-6" nativeButton={false}
                  render={<a href={sessionUrl('/history/download')} target="_blank" rel="noreferrer" />}>
            Download log (.txt)
          </Button>
        </DialogHeader>

        <div className="overflow-y-auto pr-1 -mr-1">
          {loading && <p className="text-sm text-muted-foreground">Loading…</p>}
          {error && <p className="text-sm text-grid">{error}</p>}
          {!loading && !error && cycles.length === 0 && (
            <p className="text-sm text-muted-foreground">No cycles logged on the server yet.</p>
          )}
          {cycles.slice().reverse().map((c) => (
            <div key={c.cycle} className="history-row">
              <div className="history-row-top">
                <span className="history-cycle font-display">Cycle {c.cycle}</span>
                <span className="history-time font-mono">{c.timestamp}</span>
                {c.replanned && <Badge variant="destructive" className="font-mono text-[0.6rem] uppercase">forecast missed</Badge>}
              </div>
              <div className="history-row-metrics font-mono">
                <span style={{ color: 'var(--solar)' }}>Solar {c.solar_kw} kW</span>
                <span style={{ color: 'var(--battery)' }}>Battery {c.battery_kw} kW</span>
                <span style={{ color: 'var(--grid)' }}>Grid {c.grid_kw} kW</span>
                <span className="text-muted-foreground">SOC {c.battery_soc_pct}%</span>
              </div>
              <p className="history-reasoning">"{c.reasoning}"</p>
              {c.alerts.length > 0 && <ul className="alert-list small">{c.alerts.map((a, i) => <li key={i}>{a}</li>)}</ul>}
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  )
}