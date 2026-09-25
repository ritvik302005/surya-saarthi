import { useEffect, useState, useCallback } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Separator } from '@/components/ui/separator'
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip'
import EnergyFlow from './EnergyFlow.jsx'
import PipelineStepper from './PipelineStepper.jsx'
import HistoryChart from './HistoryChart.jsx'
import HistoryModal from './HistoryModal.jsx'
import ComparisonCard from './ComparisonCard.jsx'
import SituationPanel from './SituationPanel.jsx'
import ConfirmDialog from './ConfirmDialog.jsx'
import MoreMenu from './MoreMenu.jsx'
import { useCountUp } from './useCountUp.js'
import { apiFetch, checkedJson, errorMessage, sessionUrl } from './api.js'
import { PRODUCT_NAME } from './brand.js'

const wait = (ms) => new Promise((r) => setTimeout(r, ms))

function BatteryGauge({ pct }) {
  const value = useCountUp(pct)
  const radius = 54
  const circumference = 2 * Math.PI * radius
  const offset = circumference - (Math.min(100, Math.max(0, value)) / 100) * circumference
  const low = pct <= 22

  return (
    <div className="gauge">
      <svg viewBox="0 0 140 140">
        <circle cx="70" cy="70" r={radius} className="gauge-track" />
        <circle cx="70" cy="70" r={radius} className={low ? 'gauge-fill low' : 'gauge-fill'}
          strokeDasharray={circumference} strokeDashoffset={offset} />
      </svg>
      <span className="gauge-value font-display">{value.toFixed(0)}%</span>
    </div>
  )
}

export default function Dashboard({ onBack }) {
  const [state, setState] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [cyclesRun, setCyclesRun] = useState(0)
  const [totalSavings, setTotalSavings] = useState(0)
  const [totalCarbon, setTotalCarbon] = useState(0)
  const [history, setHistory] = useState([])
  const [stepIndex, setStepIndex] = useState(-1)
  const [replanFlash, setReplanFlash] = useState(false)
  const [historyOpen, setHistoryOpen] = useState(false)

  // --- NEW: manual weather scenario + day-count batch simulation ---
  const [scenarios, setScenarios] = useState({ normal: 'Normal / mixed clouds' })
  const [scenario, setScenario] = useState('normal')
  const [days, setDays] = useState(1)
  const [simLoading, setSimLoading] = useState(false)
  const [simProgress, setSimProgress] = useState(null)   // { current, total } while running
  const [simStatusText, setSimStatusText] = useState('')  // latest reasoning, shown live
  const [simDone, setSimDone] = useState(null)            // summary banner after a finished run
  const [confirm, setConfirm] = useState(null)            // pending destructive action

  useEffect(() => { document.title = `Dashboard · ${PRODUCT_NAME}` }, [])

  useEffect(() => {
    apiFetch('/scenarios')
      .then(checkedJson)
      .then((d) => {
        if (d.scenarios) setScenarios(d.scenarios)
        if (d.default) setScenario(d.default)
      })
      .catch(() => {
        // fine to fail quietly — the dropdown just keeps its built-in default
      })
  }, [])

  // Runs live, one cycle at a time, updating the chart/state/status after
  // EACH cycle — instead of one blocking /simulate call that only shows
  // anything once the entire batch has finished. Same total wall-clock time
  // (each cycle is a real Groq call, that cost doesn't go away), but you can
  // actually see it working instead of staring at a frozen button.
  async function runSimulation() {
    setSimLoading(true); setError(null); setReplanFlash(false); setSimDone(null)
    const totalHours = days * 24
    let last = null
    setSimProgress({ current: 0, total: totalHours })
    setSimStatusText('Starting simulation…')

    try {
      await checkedJson(await apiFetch('/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario }),
      }))

      setCyclesRun(0); setTotalSavings(0); setTotalCarbon(0); setHistory([]); setStepIndex(-1)

      for (let i = 1; i <= totalHours; i++) {
        setSimProgress({ current: i, total: totalHours })

        const data = await checkedJson(await apiFetch('/cycle', { method: 'POST' }))
        last = data

        if (data.report?.replanned_this_cycle) {
          setReplanFlash(true)
          await wait(150)
          setReplanFlash(false)
        }
        setStepIndex(4)
        setState(data)
        setCyclesRun(i)
        setTotalSavings((s) => s + (data.report?.savings_rs || 0))
        setTotalCarbon((c) => c + (data.report?.carbon_avoided_kg || 0))
        setHistory((h) => [
          ...h.slice(-19),
          {
            cycle: (h.at(-1)?.cycle || 0) + 1,   // h is trimmed to 20 points, so its length can't be the cycle number
            solar: data.decision?.solar_used_kw || 0,
            battery: data.decision?.battery_used_kw || 0,
            grid: data.decision?.grid_used_kw || 0,
            replanned: !!data.report?.replanned_this_cycle,
          },
        ])
        setSimStatusText(
          `Hour ${i}/${totalHours} — solar ${(data.decision?.solar_used_kw || 0).toFixed(1)} kW, `
          + `grid ${(data.decision?.grid_used_kw || 0).toFixed(1)} kW`
          + (data.report?.replanned_this_cycle ? ' — replanned' : '')
          + (data.reasoning ? ` — "${data.reasoning}"` : '')
        )
      }
      setSimDone({ hours: totalHours, label: scenarios[scenario] || scenario, comparison: last?.comparison })
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setSimLoading(false); setSimProgress(null)
    }
  }

  // On load (or refresh), pick up this tab's session from the backend so the
  // chart and session totals don't reset to zero while the server still has them.
  const fetchState = useCallback(async () => {
    try {
      const [data, past] = await Promise.all([
        apiFetch('/state').then(checkedJson),
        apiFetch('/history').then(checkedJson),
      ])
      if (data && data.decision) { setState(data); setStepIndex(4) }
      const cycles = past.cycles || []
      setCyclesRun(cycles.length)
      setTotalSavings(cycles.reduce((s, c) => s + (c.savings_rs || 0), 0))
      setTotalCarbon(cycles.reduce((s, c) => s + (c.carbon_avoided_kg || 0), 0))
      setHistory(cycles.slice(-20).map((c) => ({
        cycle: c.cycle, solar: c.solar_kw || 0, battery: c.battery_kw || 0, grid: c.grid_kw || 0, replanned: !!c.replanned,
      })))
      if (data?.scenario) setScenario(data.scenario)
      setError(null)
    } catch (err) {
      setError(errorMessage(err))
    }
  }, [])

  useEffect(() => { fetchState() }, [fetchState])

  async function runCycle() {
    setLoading(true); setError(null); setReplanFlash(false); setStepIndex(0)

    let cancelled = false
    ;(async () => {
      for (let i = 1; i <= 3; i++) { await wait(420); if (!cancelled) setStepIndex(i) }
    })()

    try {
      const data = await checkedJson(await apiFetch('/cycle', { method: 'POST' }))
      cancelled = true

      if (data.report?.replanned_this_cycle) {
        setStepIndex(1); setReplanFlash(true)
        await wait(550); setStepIndex(3); await wait(300)
      }
      setStepIndex(4)

      setState(data)
      setCyclesRun((c) => c + 1)
      setTotalSavings((s) => s + (data.report?.savings_rs || 0))
      setTotalCarbon((c) => c + (data.report?.carbon_avoided_kg || 0))
      setHistory((h) => [
        ...h.slice(-19),
        {
          cycle: (h.at(-1)?.cycle || 0) + 1,   // h is trimmed to 20 points, so its length can't be the cycle number
          solar: data.decision.solar_used_kw || 0,
          battery: data.decision.battery_used_kw || 0,
          grid: data.decision.grid_used_kw || 0,
          replanned: !!data.report?.replanned_this_cycle,
        },
      ])
    } catch (err) {
      cancelled = true
      setError(errorMessage(err))
    } finally {
      setLoading(false); setReplanFlash(false)
    }
  }

  async function resetSession() {
    try {
      await checkedJson(await apiFetch('/reset', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ scenario }),
      }))
      setState(null); setCyclesRun(0); setTotalSavings(0); setTotalCarbon(0)
      setHistory([]); setStepIndex(-1)
    } catch (err) {
      setError(errorMessage(err))
    }
  }

  // Ask first only when there is a run to lose; a fresh session goes straight ahead.
  function requestSimulation() {
    if (cyclesRun === 0) return runSimulation()
    setConfirm({
      title: 'Start a new simulation?',
      body: `This clears the current run (${cyclesRun} hour${cyclesRun !== 1 ? 's' : ''}) and starts ${days} day${days !== 1 ? 's' : ''} of ${scenarios[scenario] || scenario}.`,
      label: 'Start simulation',
      onConfirm: runSimulation,
    })
  }

  function requestReset() {
    if (cyclesRun === 0) return resetSession()
    setConfirm({
      title: 'Reset this session?',
      body: `This clears ${cyclesRun} simulated hour${cyclesRun !== 1 ? 's' : ''}, the chart and the totals. Download the CSV first if you need the numbers.`,
      label: 'Reset session',
      onConfirm: () => { setSimDone(null); resetSession() },
    })
  }

  const decision = state?.decision || {}
  const report = state?.report || {}
  const alerts = state?.alerts || []
  const sessionSavings = useCountUp(totalSavings)
  const sessionCarbon = useCountUp(totalCarbon)

  return (
    <TooltipProvider delayDuration={200}>
      <div className="min-h-screen flex flex-col animate-in fade-in duration-500">
        <a href="#main" className="skip-link">Skip to content</a>
        <header className="sticky top-0 z-10 flex flex-wrap items-center justify-between gap-x-4 gap-y-2.5 px-4 sm:px-14 py-3 sm:py-5 border-b border-border bg-background/85 backdrop-blur-sm">
          <div className="flex items-center gap-2.5 font-display font-semibold tracking-tight">
            <span className={`h-2 w-2 rounded-full ${loading ? 'bg-solar animate-pulse' : state ? 'bg-battery' : 'bg-muted-foreground'}`} />
            {PRODUCT_NAME}
          </div>
          <div className="flex items-center gap-2 sm:gap-3 flex-wrap justify-start sm:justify-end w-full sm:w-auto">
            <div className="flex items-center gap-2 font-mono text-xs w-full sm:w-auto">
              <select
                value={scenario}
                onChange={(e) => setScenario(e.target.value)}
                disabled={simLoading}
                className="flex-1 sm:flex-none min-w-0 bg-secondary border border-border rounded-md px-2 py-1.5 text-foreground disabled:opacity-50"
                title="Manually set the weather scenario for the next run"
              >
                {Object.entries(scenarios).map(([key, label]) => (
                  <option key={key} value={key} style={{ color: '#111827', backgroundColor: '#fff' }}>{label}</option>
                ))}
              </select>
              <input
                type="number" min={1} max={7} value={days}
                onChange={(e) => setDays(Math.min(7, Math.max(1, Number(e.target.value) || 1)))}
                disabled={simLoading}
                className="w-14 bg-secondary border border-border rounded-md px-2 py-1.5 text-foreground disabled:opacity-50"
                title="Number of simulated days to run"
              />
              <span className="text-muted-foreground">day{days !== 1 ? 's' : ''}</span>
            </div>
            <Tooltip>
              <TooltipTrigger render={<Button variant="secondary" size="sm" onClick={requestSimulation} disabled={simLoading || loading} />}>
                {simLoading ? 'Simulating…' : 'Run simulation'}
              </TooltipTrigger>
              <TooltipContent>Runs the chosen scenario for the chosen number of days in one go, instead of one cycle at a time.</TooltipContent>
            </Tooltip>
            <div className="hidden sm:flex items-center gap-3">
              <Button variant="ghost" size="sm" onClick={onBack}>← Overview</Button>
              <Button variant="outline" size="sm" onClick={() => setHistoryOpen(true)}>History report</Button>
              <Tooltip>
                <TooltipTrigger render={<Button variant="outline" size="sm" onClick={requestReset} />}>
                  Reset session
                </TooltipTrigger>
                <TooltipContent>Clears this session's totals and chart. The server-side log keeps every cycle regardless.</TooltipContent>
              </Tooltip>
            </div>
            <MoreMenu items={[
              { label: '← Overview', onClick: onBack },
              { label: 'History report', onClick: () => setHistoryOpen(true) },
              { label: 'Reset session', onClick: requestReset },
            ]} />
            <Button onClick={runCycle} disabled={loading || simLoading} className="ml-auto sm:ml-0">
              {loading ? 'Computing…' : 'Run cycle'}
            </Button>
          </div>
        </header>

        {simProgress && (
          <div className="px-6 sm:px-14 py-3 border-b border-border bg-secondary/40">
            <div className="max-w-3xl mx-auto">
              <div className="flex items-center justify-between font-mono text-xs text-muted-foreground mb-1.5">
                <span>Simulating {scenarios[scenario] || scenario}…</span>
                <span>{simProgress.current}/{simProgress.total} hours</span>
              </div>
              <div className="w-full h-1.5 rounded-full bg-secondary overflow-hidden">
                <div
                  className="h-full bg-battery transition-all duration-200"
                  style={{ width: `${(simProgress.current / simProgress.total) * 100}%` }}
                />
              </div>
              {simStatusText && (
                <p className="font-mono text-xs text-muted-foreground mt-1.5 truncate">{simStatusText}</p>
              )}
            </div>
          </div>
        )}

        {simDone && (
          <div role="status" className="px-6 sm:px-14 py-3 border-b border-border bg-battery/10">
            <div className="max-w-3xl mx-auto flex items-start justify-between gap-4 text-sm">
              <p>
                <span className="font-semibold">Simulation complete:</span> {simDone.hours} hours of {simDone.label}.
                {simDone.comparison && (
                  <> {Math.abs(simDone.comparison.grid_reduction_pct).toFixed(1)}% {simDone.comparison.grid_reduction_pct >= 0 ? 'less' : 'more'} grid
                    power and ₹{simDone.comparison.extra_savings_rs.toFixed(2)} {simDone.comparison.extra_savings_rs >= 0 ? 'saved' : 'extra'} vs
                    fixed rules. Details below.</>
                )}
              </p>
              <button className="text-muted-foreground hover:text-foreground shrink-0" aria-label="Dismiss" onClick={() => setSimDone(null)}>✕</button>
            </div>
          </div>
        )}

        <main id="main" tabIndex={-1} className="outline-none">
          <section className="max-w-3xl mx-auto text-center px-6 sm:px-14 pt-16 sm:pt-24 pb-10">
            <Badge variant="outline" className="mb-5 font-mono text-[0.7rem] tracking-wider text-battery border-battery/30 uppercase">
              Live agent · SDG 7 · Clean energy
            </Badge>
            <h1 className="font-display font-semibold tracking-tight text-[clamp(2rem,4.5vw,3.4rem)] leading-[1.1] mb-4">
              Every cycle, it decides where the power comes from.
            </h1>
            <p className="text-muted-foreground text-[clamp(0.95rem,1.4vw,1.1rem)] leading-relaxed max-w-xl mx-auto mb-2">
              An AI agent reads sunlight, prices and demand, decides how to split power between
              solar, battery and grid, and replans the moment its own forecast turns out wrong.
            </p>

            <PipelineStepper stepIndex={stepIndex} replanFlash={replanFlash} />
            <p className="pipeline-caption">
              Each cycle: sense real conditions → the agent proposes a split → hard safety rules can
              override it → battery state updates → if the forecast was wrong, it loops back and
              replans before reporting.
            </p>

            {error && (
              <div className="font-mono text-sm px-5 py-4 rounded-lg border border-grid/30 text-grid max-w-md mx-auto">{error}</div>
            )}
            {!state && !error && (
              <div className="font-mono text-sm px-5 py-4 rounded-lg border border-border text-muted-foreground max-w-md mx-auto">
                No cycle has run yet. Press Run cycle to sense conditions and allocate power.
              </div>
            )}

            {state && (
              <>
                <SituationPanel state={state} scenarioLabel={scenarios[state.scenario] || state.scenario || ''} />
                <div className="legend">
                  <span><i style={{ background: 'var(--solar)' }} />Solar</span>
                  <span><i style={{ background: 'var(--battery)' }} />Battery</span>
                  <span><i style={{ background: 'var(--grid)' }} />Grid (last resort)</span>
                </div>
                <EnergyFlow
                  solarKw={decision.solar_used_kw || 0}
                  batteryKw={decision.battery_used_kw || 0}
                  gridKw={decision.grid_used_kw || 0}
                  exportKw={decision.grid_export_kw || 0}
                  criticalKw={state.critical_load_kw || 0}
                  flexibleLoads={state.flexible_loads || []}
                  loading={loading}
                />
              </>
            )}

            {state?.reasoning && (
              <blockquote className="reasoning">
                "{state.reasoning}"
                {report?.replanned_this_cycle && (
                  <Badge variant="destructive" className="mt-2.5 font-mono text-[0.65rem] tracking-wider uppercase block w-fit">
                    Replanned — forecast deviation detected
                  </Badge>
                )}
              </blockquote>
            )}
          </section>

          {state && (
            <section className="max-w-6xl mx-auto grid grid-cols-1 md:grid-cols-3 gap-px bg-border border-y border-border">
              <Card className="rounded-none border-0 gap-3.5 animate-in fade-in slide-in-from-bottom-2 duration-500">
                <CardHeader>
                  <CardTitle className="font-mono text-xs tracking-wider uppercase text-muted-foreground font-normal">Battery reserve</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-3.5">
                  <BatteryGauge pct={state.battery_soc_pct || 0} />
                  <CardDescription>Never discharges below 20% reserve — enforced regardless of what the agent proposes.</CardDescription>
                </CardContent>
              </Card>

              <Card className="rounded-none border-0 gap-3.5 animate-in fade-in slide-in-from-bottom-2 duration-500 delay-75">
                <CardHeader>
                  <CardTitle className="font-mono text-xs tracking-wider uppercase text-muted-foreground font-normal">Safety overrides this cycle</CardTitle>
                </CardHeader>
                <CardContent>
                  {alerts.length === 0 ? (
                    <CardDescription>No overrides triggered — the proposed allocation stayed within every limit.</CardDescription>
                  ) : (
                    <ul className="alert-list">{alerts.map((a, i) => <li key={i}>{a}</li>)}</ul>
                  )}
                </CardContent>
              </Card>

              <Card className="rounded-none border-0 gap-3.5 animate-in fade-in slide-in-from-bottom-2 duration-500 delay-150">
                <CardHeader>
                  <CardTitle className="font-mono text-xs tracking-wider uppercase text-muted-foreground font-normal">Session impact</CardTitle>
                </CardHeader>
                <CardContent className="flex flex-col gap-3.5">
                  <div className="flex gap-8">
                    <div>
                      <span className="block font-display text-2xl font-semibold">₹{sessionSavings.toFixed(2)}</span>
                      <span className="block text-xs text-muted-foreground mt-0.5">saved vs. grid-only baseline</span>
                    </div>
                    <div>
                      <span className="block font-display text-2xl font-semibold">{sessionCarbon.toFixed(2)} kg</span>
                      <span className="block text-xs text-muted-foreground mt-0.5">CO₂ avoided</span>
                    </div>
                  </div>
                  <Separator />
                  <CardDescription>{cyclesRun} cycle{cyclesRun !== 1 ? 's' : ''} run this session</CardDescription>
                </CardContent>
              </Card>
            </section>
          )}

          {state?.comparison && (
            <div className="mt-8">
              <ComparisonCard comparison={state.comparison} csvUrl={sessionUrl('/history/csv')} />
            </div>
          )}

          {history.length > 0 && (
            <section className="max-w-6xl mx-auto px-6 sm:px-9 mb-12">
              <Card className="p-8">
                <CardTitle className="font-mono text-xs tracking-wider uppercase text-muted-foreground font-normal mb-3">Power mix across this session</CardTitle>
                <HistoryChart history={history} />
              </Card>
            </section>
          )}
        </main>

        <footer className="mt-auto text-center py-8 border-t border-border font-mono text-xs tracking-wide text-muted-foreground">
          Sense → Allocate → Safety limits → Apply → Replan if needed → Report
        </footer>

        <HistoryModal open={historyOpen} onOpenChange={setHistoryOpen} />
        <ConfirmDialog confirm={confirm} onClose={() => setConfirm(null)} />
      </div>
    </TooltipProvider>
  )
}