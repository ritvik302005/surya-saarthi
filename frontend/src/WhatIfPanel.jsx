import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardTitle, CardDescription } from '@/components/ui/card'
import { apiFetch, checkedJson, errorMessage } from './api.js'

const HOURS = Array.from({ length: 24 }, (_, h) => h)
const hh = (h) => `${String(h).padStart(2, '0')}:00`

const T = {
  en: {
    title: 'What if…', run: 'Run what-if', running: 'Running…',
    desc: 'Replays the next 24 hours from now with changed conditions. No AI calls: the optimizer and the fixed rule, same clouds and demand.',
    sun: 'Sunshine', cut: 'Power cut', from: 'from', to: 'to', health: 'Battery health', peak: 'Evening peak price',
    extra: 'Extra essential load', dr: 'DISCOM grid limit', max: 'max',
    cols: ['Now (optimizer)', 'What-if (optimizer)', 'What-if (fixed rule)'],
    rows: ['Cost for 24 h (change in battery charge counted)', 'Grid power bought', 'Diesel used', 'Essential load not served', 'Lowest battery level'],
    chart: 'Battery level over the next 24 hours',
  },
  hi: {
    title: 'अगर ऐसा हो तो…', run: 'चलाएँ', running: 'चल रहा है…',
    desc: 'अभी से अगले 24 घंटे बदली हुई स्थिति में दोबारा चलाता है। कोई AI कॉल नहीं: ऑप्टिमाइज़र और तय नियम, एक जैसे बादल और माँग।',
    sun: 'धूप', cut: 'बिजली कटौती', from: 'से', to: 'तक', health: 'बैटरी की सेहत', peak: 'शाम का पीक दाम',
    extra: 'अतिरिक्त ज़रूरी लोड', dr: 'DISCOM ग्रिड सीमा', max: 'अधिकतम',
    cols: ['अभी (ऑप्टिमाइज़र)', 'अगर (ऑप्टिमाइज़र)', 'अगर (तय नियम)'],
    rows: ['24 घंटे का ख़र्च (बैटरी चार्ज का बदलाव गिना गया)', 'ग्रिड से ली बिजली', 'डीज़ल', 'ज़रूरी लोड जो नहीं चला', 'बैटरी का सबसे कम स्तर'],
    chart: 'अगले 24 घंटे बैटरी का स्तर',
  },
}

function HourSelect({ id, value, onChange, label }) {
  return (
    <>
      <label htmlFor={id} className="sr-only">{label}</label>
      <select id={id} value={value} onChange={(e) => onChange(Number(e.target.value))}
              className="bg-secondary border border-border rounded-md px-1.5 py-1 font-mono text-xs text-foreground">
        {HOURS.map((h) => <option key={h} value={h} style={{ color: '#111827', backgroundColor: '#fff' }}>{hh(h)}</option>)}
      </select>
    </>
  )
}

function Slider({ id, label, value, min, max, step, onChange, show }) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={id} className="flex justify-between font-mono text-[0.7rem] text-muted-foreground">
        <span>{label}</span><span className="text-foreground">{show(value)}</span>
      </label>
      <input id={id} type="range" min={min} max={max} step={step} value={value}
             onChange={(e) => onChange(Number(e.target.value))} className="w-full accent-[var(--battery)]" />
    </div>
  )
}

function SocChart({ runs, title }) {
  const W = 480, H = 120, colors = ['var(--muted-foreground)', 'var(--battery)', 'var(--grid)']
  const x = (i) => (i / 23) * (W - 20) + 10
  const y = (pct) => H - 10 - (pct / 100) * (H - 20)
  return (
    <figure className="mt-2">
      <svg viewBox={`0 0 ${W} ${H}`} className="w-full h-auto" role="img" aria-label={title}>
        {[20, 100].map((p) => (
          <g key={p}>
            <line x1="10" x2={W - 10} y1={y(p)} y2={y(p)} stroke="var(--border)" strokeDasharray="3 4" />
            <text x={W - 8} y={y(p) + 3} fontSize="9" fill="var(--muted-foreground)" textAnchor="end">{p}%</text>
          </g>
        ))}
        {runs.map((run, r) => (
          <polyline key={r} fill="none" stroke={colors[r]} strokeWidth={r === 1 ? 2.5 : 1.8}
                    points={run.hourly.map((h, i) => `${x(i)},${y(h.soc_pct)}`).join(' ')} />
        ))}
      </svg>
      <figcaption className="font-mono text-[0.7rem] text-muted-foreground">{title}</figcaption>
    </figure>
  )
}

export default function WhatIfPanel({ lang = 'en' }) {
  const t = T[lang] || T.en
  const [solar, setSolar] = useState(60)
  const [cut, setCut] = useState(true)
  const [cutStart, setCutStart] = useState(19)
  const [cutEnd, setCutEnd] = useState(22)
  const [health, setHealth] = useState(100)
  const [peak, setPeak] = useState(1.2)
  const [extra, setExtra] = useState(0)
  const [dr, setDr] = useState(false)
  const [drStart, setDrStart] = useState(18)
  const [drEnd, setDrEnd] = useState(20)
  const [drCap, setDrCap] = useState(1)
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  async function run() {
    setBusy(true); setError(null)
    const body = { solar_scale: solar / 100, battery_health_pct: health, peak_multiplier: peak, extra_load_kw: extra }
    if (cut) body.outage = { start: cutStart, end: cutEnd }
    if (dr) body.dr = { start: drStart, end: drEnd, max_grid_kw: drCap }
    try {
      setResult(await checkedJson(await apiFetch('/whatif', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      })))
    } catch (err) {
      setError(errorMessage(err))
    } finally {
      setBusy(false)
    }
  }

  const runs = result ? [result.now, result.what_if, result.what_if_rule] : []
  const metrics = [
    (r) => `₹${r.totals.adjusted_cost_rs.toFixed(0)}`,
    (r) => `${r.totals.grid_kwh.toFixed(1)} kWh`,
    (r) => `${r.totals.diesel_l.toFixed(1)} L`,
    (r) => `${r.totals.unserved_kwh.toFixed(1)} kWh`,
    (r) => `${r.totals.min_soc_pct.toFixed(0)}%`,
  ]

  return (
    <Card className="p-6 sm:p-8 gap-4">
      <div>
        <CardTitle className="font-mono text-xs tracking-wider uppercase text-muted-foreground font-normal mb-1.5">{t.title}</CardTitle>
        <CardDescription>{t.desc}</CardDescription>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-6 gap-y-3">
        <Slider id="wi-sun" label={t.sun} value={solar} min={0} max={150} step={10} onChange={setSolar} show={(v) => `${v}%`} />
        <Slider id="wi-health" label={t.health} value={health} min={50} max={100} step={5} onChange={setHealth} show={(v) => `${v}%`} />
        <Slider id="wi-peak" label={t.peak} value={peak} min={1} max={2} step={0.1} onChange={setPeak} show={(v) => `×${v.toFixed(1)} (₹${(8 * v).toFixed(2)})`} />
        <Slider id="wi-extra" label={t.extra} value={extra} min={0} max={5} step={0.5} onChange={setExtra} show={(v) => `+${v} kW`} />
        <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
          <input id="wi-cut" type="checkbox" checked={cut} onChange={(e) => setCut(e.target.checked)} className="accent-[var(--battery)]" />
          <label htmlFor="wi-cut">{t.cut}</label>
          <span className="text-muted-foreground">{t.from}</span>
          <HourSelect id="wi-cut-start" value={cutStart} onChange={setCutStart} label={`${t.cut} ${t.from}`} />
          <span className="text-muted-foreground">{t.to}</span>
          <HourSelect id="wi-cut-end" value={cutEnd} onChange={setCutEnd} label={`${t.cut} ${t.to}`} />
        </div>
        <div className="flex flex-wrap items-center gap-2 font-mono text-xs">
          <input id="wi-dr" type="checkbox" checked={dr} onChange={(e) => setDr(e.target.checked)} className="accent-[var(--battery)]" />
          <label htmlFor="wi-dr">{t.dr}</label>
          <HourSelect id="wi-dr-start" value={drStart} onChange={setDrStart} label={`${t.dr} ${t.from}`} />
          <span className="text-muted-foreground">–</span>
          <HourSelect id="wi-dr-end" value={drEnd} onChange={setDrEnd} label={`${t.dr} ${t.to}`} />
          <label htmlFor="wi-dr-cap" className="text-muted-foreground">{t.max}</label>
          <input id="wi-dr-cap" type="number" min={0} max={20} step={0.5} value={drCap} onChange={(e) => setDrCap(Number(e.target.value) || 0)}
                 className="w-14 bg-secondary border border-border rounded-md px-1.5 py-1 text-foreground" />
          <span className="text-muted-foreground">kW</span>
        </div>
      </div>

      <div>
        <Button size="sm" onClick={run} disabled={busy}>{busy ? t.running : t.run}</Button>
      </div>
      {error && <p className="font-mono text-xs text-grid" role="alert">{error}</p>}

      {result && (
        <div className="flex flex-col gap-3 pt-3 border-t border-border">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="font-mono text-[0.7rem] text-muted-foreground">
                  <th className="text-left font-normal py-1.5 pr-3"><span className="sr-only">Metric</span></th>
                  {t.cols.map((col, i) => (
                    <th key={col} className="text-right font-normal py-1.5 px-2">
                      <span className="inline-block w-2 h-2 rounded-full mr-1.5" style={{ background: ['var(--muted-foreground)', 'var(--battery)', 'var(--grid)'][i] }} />{col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {t.rows.map((row, i) => (
                  <tr key={row} className="border-t border-border">
                    <th scope="row" className="text-left font-normal text-muted-foreground py-1.5 pr-3">{row}</th>
                    {runs.map((r, j) => <td key={j} className="text-right font-mono py-1.5 px-2">{metrics[i](r)}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <SocChart runs={runs} title={t.chart} />
        </div>
      )}
    </Card>
  )
}
