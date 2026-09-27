import { useState, useMemo } from 'react'

const WIDTH = 640
const HEIGHT = 220
const PAD = 28

export default function HistoryChart({ history }) {
  const [hoverIdx, setHoverIdx] = useState(null)

  const maxKw = useMemo(() => {
    const all = history.flatMap((h) => [h.solar, h.battery, h.grid])
    return Math.max(4, ...all) * 1.15
  }, [history])

  const n = history.length
  const x = (i) => (n <= 1 ? PAD : PAD + (i / (n - 1)) * (WIDTH - PAD * 2))
  const y = (v) => HEIGHT - PAD - (v / maxKw) * (HEIGHT - PAD * 2)

  function linePath(key) {
    return history.map((h, i) => `${i === 0 ? 'M' : 'L'} ${x(i)} ${y(h[key])}`).join(' ')
  }

  function handleMove(e) {
    if (n === 0) return
    const rect = e.currentTarget.getBoundingClientRect()
    const relX = ((e.clientX - rect.left) / rect.width) * WIDTH
    let idx = Math.round(((relX - PAD) / (WIDTH - PAD * 2)) * (n - 1))
    idx = Math.max(0, Math.min(n - 1, idx))
    setHoverIdx(idx)
  }

  if (n === 0) {
    return <p className="panel-empty">Run a few hours to see the trend build up here.</p>
  }

  const hovered = hoverIdx !== null ? history[hoverIdx] : history[n - 1]

  return (
    <div className="history-chart">
      <svg
        viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
        onMouseMove={handleMove}
        onMouseLeave={() => setHoverIdx(null)}
        className="history-svg"
      >
        {[0.25, 0.5, 0.75].map((f) => (
          <line key={f} x1={PAD} x2={WIDTH - PAD} y1={PAD + f * (HEIGHT - PAD * 2)} y2={PAD + f * (HEIGHT - PAD * 2)} className="grid-line" />
        ))}

        <path d={linePath('solar')} className="hist-line" stroke="var(--solar)" fill="none" />
        <path d={linePath('battery')} className="hist-line" stroke="var(--battery)" fill="none" />
        <path d={linePath('grid')} className="hist-line" stroke="var(--grid)" fill="none" />

        {/* A dot per cycle for every series — without this, a chart with only
            one or two cycles run so far draws literally nothing, since an SVG
            path needs at least two points to have a visible line segment. */}
        {history.map((h, i) => (
          <g key={`dots-${i}`}>
            <circle cx={x(i)} cy={y(h.solar)} r="2.5" fill="var(--solar)" />
            <circle cx={x(i)} cy={y(h.battery)} r="2.5" fill="var(--battery)" />
            <circle cx={x(i)} cy={y(h.grid)} r="2.5" fill="var(--grid)" />
          </g>
        ))}

        {history.map(
          (h, i) =>
            h.replanned && (
              <circle key={`replan-${i}`} cx={x(i)} cy={y(h.battery)} r="5"
                      fill="none" stroke="var(--grid)" strokeWidth="1.5" />
            )
        )}

        {hoverIdx !== null && <line x1={x(hoverIdx)} x2={x(hoverIdx)} y1={PAD} y2={HEIGHT - PAD} className="hover-line" />}
      </svg>

      <div className="chart-tooltip">
        <span className="tooltip-cycle">Cycle {hovered.cycle}</span>
        <span style={{ color: 'var(--solar)' }}>Solar {hovered.solar.toFixed(1)} kW</span>
        <span style={{ color: 'var(--battery)' }}>Battery {hovered.battery.toFixed(1)} kW</span>
        <span style={{ color: 'var(--grid)' }}>Grid {hovered.grid.toFixed(1)} kW</span>
        {hovered.replanned && <span className="tooltip-replanned">forecast missed</span>}
      </div>
    </div>
  )
}