import { useEffect, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardTitle, CardDescription } from '@/components/ui/card'
import { apiFetch, checkedJson, errorMessage } from './api.js'

const EXAMPLES = ['aaj shaam 7 se 10 bijli jayegi', 'battery full by 6 pm', 'DISCOM: grid max 2 kW 6-8 pm']

const T = {
  en: {
    title: 'Tell it what’s coming',
    desc: 'Type a note in Hindi, Hinglish or English: a power cut, a battery target, or a grid limit from the DISCOM. It shows what it understood; nothing changes until you confirm.',
    label: 'Operator note', understand: 'Understand', apply: 'Apply', cancel: 'Cancel',
    readBy: { ai: 'Read by the AI', rules: 'Read by the rule-based parser' },
    active: 'Active', none: 'No power cuts, targets or grid limits set.', clear: 'Clear',
    test: 'Test the battery safety:', overheat: 'Simulate overheating', sensor: 'Simulate lost sensor', fixed: 'Clear fault',
  },
  hi: {
    title: 'आगे क्या होने वाला है, बताइए',
    desc: 'हिंदी, हिंग्लिश या अंग्रेज़ी में लिखिए: बिजली कटौती, बैटरी का लक्ष्य, या DISCOM की ग्रिड सीमा। यह बताएगा कि क्या समझा; आपकी पुष्टि के बिना कुछ नहीं बदलेगा।',
    label: 'ऑपरेटर नोट', understand: 'समझें', apply: 'लागू करें', cancel: 'रद्द करें',
    readBy: { ai: 'AI ने पढ़ा', rules: 'नियम-आधारित पार्सर ने पढ़ा' },
    active: 'लागू', none: 'कोई बिजली कटौती, लक्ष्य या ग्रिड सीमा नहीं।', clear: 'हटाएँ',
    test: 'बैटरी सुरक्षा जाँचें:', overheat: 'ज़्यादा गर्मी', sensor: 'सेंसर बंद', fixed: 'ठीक करें',
  },
}

const when = (simHour, now, lang) => {
  const day = Math.floor(simHour / 24) - Math.floor(now / 24)
  const word = lang === 'hi' ? (day === 0 ? 'आज' : day === 1 ? 'कल' : `दिन ${Math.floor(simHour / 24) + 1}`)
    : (day === 0 ? 'today' : day === 1 ? 'tomorrow' : `day ${Math.floor(simHour / 24) + 1}`)
  return `${word} ${String(simHour % 24).padStart(2, '0')}:00`
}

export default function OperatorPanel({ lang = 'en', onChange }) {
  const t = T[lang] || T.en
  const [text, setText] = useState('')
  const [reading, setReading] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const [c, setC] = useState(null)

  useEffect(() => { apiFetch('/constraints').then(checkedJson).then(setC).catch(() => {}) }, [])

  async function post(path, body) {
    setBusy(true); setError(null)
    try {
      return await checkedJson(await apiFetch(path, {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body),
      }))
    } catch (err) {
      setError(errorMessage(err))
      return null
    } finally {
      setBusy(false)
    }
  }

  async function understand(e) {
    e.preventDefault()
    if (!text.trim()) return
    setReading(null)
    const r = await post('/note/interpret', { text })
    if (r) setReading(r)
  }

  async function apply() {
    const r = await post('/note/apply', { actions: reading.actions })
    if (r) { setC(r); setReading(null); setText(''); onChange?.() }
  }

  async function clear(kind) {
    const r = await post('/constraints/clear', { kind })
    if (r) { setC(r); onChange?.() }
  }

  async function fault(f) {
    const r = await post('/bms/fault', { fault: f })
    if (r) { setC(r); onChange?.() }
  }

  const now = c?.now_hour ?? 0
  const items = c ? [
    ...c.outages.map(([s, e]) => ({ kind: 'outage', text: lang === 'hi' ? `बिजली कटौती ${when(s, now, lang)}–${String(e % 24).padStart(2, '0')}:00` : `Power cut ${when(s, now, lang)}–${String(e % 24).padStart(2, '0')}:00` })),
    ...c.soc_targets.map((x) => ({ kind: 'soc_target', text: lang === 'hi' ? `${when(x.hour, now, lang)} तक बैटरी ≥ ${x.min_pct}%` : `Battery ≥ ${x.min_pct}% by ${when(x.hour, now, lang)}` })),
    ...c.dr_events.map((x) => ({ kind: 'dr', text: lang === 'hi' ? `ग्रिड ≤ ${x.max_grid_kw} kW, ${when(x.start, now, lang)}–${String(x.end % 24).padStart(2, '0')}:00` : `Grid ≤ ${x.max_grid_kw} kW, ${when(x.start, now, lang)}–${String(x.end % 24).padStart(2, '0')}:00` })),
  ] : []

  return (
    <Card className="p-6 sm:p-8 gap-4">
      <div>
        <CardTitle className="font-mono text-xs tracking-wider uppercase text-muted-foreground font-normal mb-1.5">{t.title}</CardTitle>
        <CardDescription>{t.desc}</CardDescription>
      </div>

      <form onSubmit={understand} className="flex flex-col sm:flex-row gap-2">
        <label htmlFor="operator-note" className="sr-only">{t.label}</label>
        <input id="operator-note" value={text} onChange={(e) => setText(e.target.value)} maxLength={300}
               placeholder={EXAMPLES[0]} disabled={busy}
               className="flex-1 min-w-0 bg-secondary border border-border rounded-md px-3 py-2 text-sm text-foreground" />
        <Button type="submit" size="sm" disabled={busy || !text.trim()}>{busy ? '…' : t.understand}</Button>
      </form>
      <div className="flex flex-wrap gap-2">
        {EXAMPLES.map((ex) => (
          <button key={ex} type="button" onClick={() => setText(ex)}
                  className="font-mono text-[0.7rem] px-2.5 py-1 rounded-full border border-border text-muted-foreground hover:text-foreground">
            {ex}
          </button>
        ))}
      </div>

      {error && <p className="font-mono text-xs text-grid" role="alert">{error}</p>}

      {reading && (
        <div className="rounded-lg border border-battery/40 bg-battery/5 p-4 flex flex-col gap-2" role="status">
          <ul className="text-sm flex flex-col gap-1">
            {(lang === 'hi' ? reading.summary_hi : reading.summary_en).map((s) => <li key={s}>• {s}</li>)}
          </ul>
          <span className="font-mono text-[0.7rem] text-muted-foreground">{t.readBy[reading.source]}</span>
          <div className="flex gap-2">
            <Button size="sm" onClick={apply} disabled={busy}>{t.apply}</Button>
            <Button size="sm" variant="ghost" onClick={() => setReading(null)} disabled={busy}>{t.cancel}</Button>
          </div>
        </div>
      )}

      <div className="flex flex-col gap-2 pt-3 border-t border-border">
        <span className="font-mono text-[0.7rem] tracking-wider uppercase text-muted-foreground">{t.active}</span>
        {items.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t.none}</p>
        ) : (
          <ul className="flex flex-col gap-1.5">
            {items.map((it, i) => (
              <li key={i} className="flex items-center justify-between gap-3 text-sm">
                <span>{it.text}</span>
                <button type="button" onClick={() => clear(it.kind)} className="font-mono text-[0.7rem] underline underline-offset-4 text-muted-foreground hover:text-foreground">{t.clear}</button>
              </li>
            ))}
          </ul>
        )}
        <div className="flex flex-wrap items-center gap-2 mt-1 font-mono text-[0.7rem] text-muted-foreground">
          <span>{t.test}</span>
          <button type="button" onClick={() => fault('overtemp')} disabled={busy} aria-pressed={c?.bms_fault === 'overtemp'}
                  className={`px-2.5 py-1 rounded-full border ${c?.bms_fault === 'overtemp' ? 'border-grid text-grid' : 'border-border hover:text-foreground'}`}>{t.overheat}</button>
          <button type="button" onClick={() => fault('sensor_lost')} disabled={busy} aria-pressed={c?.bms_fault === 'sensor_lost'}
                  className={`px-2.5 py-1 rounded-full border ${c?.bms_fault === 'sensor_lost' ? 'border-grid text-grid' : 'border-border hover:text-foreground'}`}>{t.sensor}</button>
          {c?.bms_fault && <button type="button" onClick={() => fault(null)} className="px-2.5 py-1 rounded-full border border-border hover:text-foreground">{t.fixed}</button>}
        </div>
      </div>
    </Card>
  )
}
