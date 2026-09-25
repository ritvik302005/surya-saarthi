import summary from './data/results-summary.json'

// Headline numbers straight from backend/run_scenarios.py output — nothing here
// is typed in by hand. Hidden until a validated run has been saved.
const range = (values, digits = 0) => {
  const lo = Math.min(...values).toFixed(digits)
  const hi = Math.max(...values).toFixed(digits)
  return lo === hi ? lo : `${lo}–${hi}`
}

export default function ResultsStrip() {
  const runs = Object.values(summary.scenarios || {})
  if (runs.length === 0) return null

  const hours = runs.reduce((s, r) => s + r.hours, 0)
  const outages = runs.reduce((s, r) => s + r.essential_outage_hours, 0)
  const perDay = runs.reduce((s, r) => s + r.extra_savings_rs_per_day, 0) / runs.length
  const days = runs[0].days

  const stats = [
    { value: `${range(runs.map((r) => r.cost_reduction_pct))}%`, label: 'lower electricity cost than a fixed-rule controller' },
    { value: `${range(runs.map((r) => r.grid_reduction_pct))}%`, label: 'less power bought from the grid' },
    { value: `₹${perDay.toFixed(0)}`, label: 'saved per day on average vs fixed rules' },
    { value: String(outages), label: `essential-load outages in ${hours} simulated hours` },
  ]

  return (
    <section className="results-strip" aria-label="Simulation results">
      <div className="results-grid">
        {stats.map((s) => (
          <div key={s.label} className="result-tile">
            <span className="result-value font-display">{s.value}</span>
            <span className="result-label">{s.label}</span>
          </div>
        ))}
      </div>
      <p className="results-note">
        Simulated on real Delhi weather data, {days} day{days !== 1 ? 's' : ''} per weather type
        ({runs.map((r) => r.label.toLowerCase()).join(', ')}), same sunlight and demand for both controllers.
        Assumptions are listed in the project README.
      </p>
    </section>
  )
}
