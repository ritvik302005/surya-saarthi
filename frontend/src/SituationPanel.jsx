const BAND_STYLE = {
  'solar hours': { text: 'Solar hours (cheap)', className: 'text-battery' },
  peak: { text: 'Evening peak (costly)', className: 'text-grid' },
  normal: { text: 'Normal rate', className: 'text-muted-foreground' },
}

function Tile({ label, value, sub, valueClass = '' }) {
  return (
    <div className="flex flex-col gap-1 px-4 py-3 rounded-lg border border-border bg-secondary/30 text-left min-w-0">
      <span className="font-mono text-[0.65rem] tracking-wider uppercase text-muted-foreground">{label}</span>
      <span className={`font-display text-lg font-semibold leading-tight ${valueClass}`}>{value}</span>
      {sub && <span className="text-xs text-muted-foreground leading-snug">{sub}</span>}
    </div>
  )
}

// What the agent saw this cycle — so a viewer can see *why* it decided what it did.
export default function SituationPanel({ state, scenarioLabel }) {
  const hour = state.sim_hour ?? 0
  const day = Math.floor(hour / 24) + 1
  const band = BAND_STYLE[state.price_band] || BAND_STYLE.normal
  const expected = state.previous_forecast_kw
  const solarNow = state.solar_kw ?? 0
  const surprise = expected != null && Math.abs(solarNow - expected) > 1
  const waiting = (state.flexible_loads || []).filter((l) => l.deferred).length
  const running = (state.flexible_loads || []).filter((l) => !l.deferred)

  return (
    <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 max-w-3xl mx-auto mb-8">
      <Tile label="Time" value={`${String(hour % 24).padStart(2, '0')}:00`} sub={`Day ${day} · ${scenarioLabel}`} />
      <Tile
        label="Sunlight"
        value={`${solarNow.toFixed(1)} kW`}
        sub={expected == null ? 'first reading' : surprise
          ? `forecast said ${expected.toFixed(1)} kW, so it replans`
          : `forecast said ${expected.toFixed(1)} kW`}
        valueClass={surprise ? 'text-grid' : 'text-solar'}
      />
      <Tile label="Grid price" value={`₹${(state.grid_price_per_kwh ?? 0).toFixed(2)}/kWh`} sub={band.text} valueClass={band.className} />
      <Tile
        label="Demand"
        value={`${(state.critical_load_kw ?? 0).toFixed(1)} kW essential`}
        sub={[
          running.length ? `${running.length} flexible job${running.length > 1 ? 's' : ''} running` : null,
          waiting ? `${waiting} waiting for a better hour` : null,
        ].filter(Boolean).join(' · ') || 'no flexible jobs'}
      />
    </div>
  )
}
