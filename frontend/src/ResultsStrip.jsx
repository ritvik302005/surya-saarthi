import summary from './data/results-summary.json'

// Headline numbers straight from backend/benchmark.py output — nothing here is typed
// in by hand. Hidden until a benchmark has been run.
export default function ResultsStrip() {
  const normal = summary.conditions?.['grid normal']
  const cuts = summary.conditions?.['evening cuts']
  if (!normal) return null

  const stats = [
    { value: `${normal.cost_reduction_pct.toFixed(0)}%`, label: 'lower running cost than a fixed-rule controller (grid normal)' },
    cuts && { value: `${cuts.cost_reduction_pct.toFixed(0)}%`, label: 'lower cost with a daily 3-hour evening power cut' },
    cuts && { value: `${cuts.diesel_l.optimizer.toFixed(0)} L`, label: `diesel, vs ${cuts.diesel_l.fixed.toFixed(0)} L for the fixed rule, over the same four weeks of cuts` },
    { value: String((normal.overrides ?? 0) + (cuts?.overrides ?? 0)), label: `safety-rule overrides of the optimizer's plans in ${normal.hours + (cuts?.hours ?? 0)} simulated hours` },
  ].filter(Boolean)

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
        Simulated, not measured: a 10 kW solar, 10 kWh battery site on recorded Delhi weather
        ({summary.days} days in each of {summary.seasons.length} seasons, with the day-ahead forecast that was actually issued),
        simulated demand, same conditions for both controllers. Costs include battery wear and diesel; the power-cut
        schedule is illustrative. Assumptions are listed in the project README.
        {summary.generated_at && (
          <span className="results-date">Results generated on {new Date(summary.generated_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'long', year: 'numeric' })}.</span>
        )}
      </p>
    </section>
  )
}
