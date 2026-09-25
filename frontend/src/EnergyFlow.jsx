import { useCountUp } from './useCountUp'

function clampWidth(kw) {
  return Math.max(2, Math.min(16, 2 + kw * 2.4))
}

function Node({ x, y, r, label, value, unit, color, dim }) {
  return (
    <g transform={`translate(${x}, ${y})`} className={dim ? 'flow-node dim' : 'flow-node'}>
      <circle r={r} fill="var(--bg-panel)" stroke={color} strokeWidth="2" />
      <text y={-r - 14} textAnchor="middle" className="node-label">{label}</text>
      <text y="-2" textAnchor="middle" className="node-value" style={{ fill: color }}>{value}</text>
      <text y="16" textAnchor="middle" className="node-unit">{unit}</text>
    </g>
  )
}

export default function EnergyFlow({ solarKw = 0, batteryKw = 0, gridKw = 0, exportKw = 0, criticalKw = 0, flexibleLoads = [], loading }) {
  const totalLoad = criticalKw + flexibleLoads.filter(l => !l.deferred).reduce((s, l) => s + l.power_kw, 0)
  const deferred = flexibleLoads.filter(l => l.deferred)

  const solar = useCountUp(solarKw)
  const battery = useCountUp(Math.abs(batteryKw))
  const charging = batteryKw < -0.05
  const grid = useCountUp(gridKw)
  const load = useCountUp(totalLoad)

  const edges = [
    { from: [150, 90], kw: solarKw, color: 'var(--solar)', label: 'solar' },
    { from: [150, 210], kw: Math.max(0, batteryKw), color: 'var(--battery)', label: 'battery' },
    { from: [150, 330], kw: gridKw, color: 'var(--grid)', label: 'grid' },
  ]
  const to = [640, 210]

  return (
    <div className="energy-flow" aria-label="Live power allocation from solar, battery, and grid to the load">
      <svg viewBox="0 0 760 420" className={loading ? 'flow-svg computing' : 'flow-svg'}>
        {edges.map((e) => {
          const [x1, y1] = e.from
          const [x2, y2] = to
          const active = e.kw > 0.05
          const d = `M${x1},${y1} C ${x1 + 240},${y1} ${x2 - 200},${y2} ${x2},${y2}`
          return (
            <path
              key={e.label}
              d={d}
              className={active ? 'flow-path active' : 'flow-path'}
              stroke={e.color}
              strokeWidth={clampWidth(e.kw)}
              fill="none"
            />
          )
        })}

        {charging && (
          <path d="M112,104 C 78,135 78,165 112,196" className="flow-path active" stroke="var(--solar)"
                strokeWidth={clampWidth(-batteryKw)} fill="none" />
        )}

        <Node x={150} y={90} r={40} label="SOLAR" value={solar.toFixed(1)} unit="kW" color="var(--solar)" dim={solarKw <= 0.05} />
        <Node x={150} y={210} r={40} label="BATTERY" value={battery.toFixed(1)} unit={charging ? 'kW in' : 'kW'} color="var(--battery)" dim={Math.abs(batteryKw) <= 0.05} />
        <Node x={150} y={330} r={40} label="GRID" value={grid.toFixed(1)} unit="kW" color="var(--grid)" dim={gridKw <= 0.05} />
        {exportKw > 0.05 && (
          <text x={150} y={392} textAnchor="middle" className="node-unit" style={{ fill: 'var(--solar)' }}>
            ↑ exporting {exportKw.toFixed(1)} kW
          </text>
        )}

        <g transform="translate(640, 210)" className="flow-node load-node">
          <circle r="56" fill="var(--bg-panel)" stroke="var(--text-primary)" strokeWidth="2" />
          <text y={-70} textAnchor="middle" className="node-label">LOAD</text>
          <text y="-6" textAnchor="middle" className="node-value load">{load.toFixed(1)}</text>
          <text y="18" textAnchor="middle" className="node-unit">kW total</text>
        </g>
      </svg>

      {deferred.length > 0 && (
        <div className="deferred-strip">
          <span className="deferred-label">Deferred this cycle</span>
          {deferred.map((l) => (
            <span key={l.name} className="deferred-chip">{l.name.replace('_', ' ')} · until {l.deadline}</span>
          ))}
        </div>
      )}
    </div>
  )
}