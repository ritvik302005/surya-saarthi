import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { LiquidButton } from '@/components/ui/liquid-glass-button'
import { Sun, BatteryCharging, UtilityPole, Fuel, Droplets, CarFront, House, GraduationCap, Tractor } from 'lucide-react'
import ResultsStrip from './ResultsStrip.jsx'
import { FallbackBoundary, hasWebGL } from './webgl.jsx'
import results from './data/results-summary.json'
import { PRODUCT_NAME, TAGLINE, REPO_URL, SIH_PS_ID, SIH_PS_TITLE, TEAM_NAME } from './brand.js'
import './Landing.css'

// The animated backgrounds pull in three.js and simplex-noise; load them after
// the page is up so the first paint doesn't wait on ~500 KB of decoration.
const WebGLShader = lazy(() => import('@/components/ui/web-gl-shader').then((m) => ({ default: m.WebGLShader })))
const Waves = lazy(() => import('@/components/ui/wave-background').then((m) => ({ default: m.Waves })))

function usePrefersReducedMotion() {
  const [reduced, setReduced] = useState(false)
  useEffect(() => {
    setReduced(window.matchMedia('(prefers-reduced-motion: reduce)').matches)
  }, [])
  return reduced
}

function useReveal(threshold = 0.2) {
  const ref = useRef(null)
  const [visible, setVisible] = useState(false)
  useEffect(() => {
    const node = ref.current
    if (!node) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setVisible(true); return }
    const observer = new IntersectionObserver(
      ([entry]) => { if (entry.isIntersecting) { setVisible(true); observer.disconnect() } },
      { threshold }
    )
    observer.observe(node)
    return () => observer.disconnect()
  }, [threshold])
  return [ref, visible]
}

function Reveal({ children, className = '', delay = 0 }) {
  const [ref, visible] = useReveal()
  return (
    <div ref={ref} className={`reveal ${visible ? 'revealed' : ''} ${className}`} style={{ transitionDelay: visible ? `${delay}ms` : '0ms' }}>
      {children}
    </div>
  )
}

const STAGES = [
  { name: 'Sense', desc: 'Reads sunlight and air temperature for the site from a weather service, plus a 24-hour forecast, the battery management system’s live limits, any scheduled power cut, and the demand profile.' },
  { name: 'Check forecast', desc: 'Compares this hour’s real sunlight with what it forecast an hour ago. If it missed by more than 1 kW, this hour is planned more cautiously.' },
  { name: 'Decide', desc: 'A 24-hour optimizer plans solar, battery, grid, diesel genset and flexible jobs together, and plans again every hour. An AI (LLM) mode can decide instead, for comparison.' },
  { name: 'Safety and battery limits', desc: 'Hard rules check every decision: never below the 20% reserve or past the battery’s live limits, essentials always powered, no grid in a power cut, jobs done by their deadline.' },
  { name: 'Apply', desc: 'The battery charge updates once, by exactly what was decided (with charge and discharge losses), and waiting jobs carry forward.' },
  { name: 'Explain and report', desc: 'Explains the decision in plain English or Hindi from the plan’s own numbers, and compares it live with a fixed-rule controller on the same conditions.' },
]

const MANAGES = [
  { icon: Sun, name: 'Solar panels', desc: 'Uses sunshine first, with real losses and heat derating, and a 24-hour forecast.', color: 'text-solar' },
  { icon: BatteryCharging, name: 'Battery', desc: 'Saves sun for the evening peak and for power cuts. Counts wear and losses; never below 20%.', color: 'text-battery' },
  { icon: UtilityPole, name: 'Grid', desc: 'Buys only what solar and battery can’t cover; exports the rest under net metering.', color: 'text-grid' },
  { icon: Fuel, name: 'Diesel genset', desc: 'Only in a power cut, and as little as possible: the battery is filled before the cut starts.', color: 'text-genset' },
  { icon: Droplets, name: 'Water pump', desc: 'A flexible job: waits for sunshine, but always runs before its deadline.', color: 'text-battery' },
  { icon: CarFront, name: 'EV charging', desc: 'Moved out of the peak-price hours, finished by morning.', color: 'text-solar' },
]

const AUDIENCE = [
  { icon: House, name: 'Homes with solar and backup', desc: 'Rooftop solar homes (e.g. under PM Surya Ghar) with an inverter battery for power cuts: essentials stay on, bills go down.' },
  { icon: GraduationCap, name: 'Schools, clinics and small businesses', desc: 'Solar, battery and a diesel genset: keep essentials on through cuts with less diesel, and move pumps and EV charging to cheaper hours.' },
  { icon: Tractor, name: 'Village and farm mini-grids', desc: 'Reliable essential supply, solar pumps run on sunshine, and plain-language explanations for the operator in Hindi.' },
]

const normal = results.conditions?.['grid normal']
const cuts = results.conditions?.['evening cuts']

const FAQ = [
  { q: 'Is this running on real data?', a: 'Sunlight and temperature are real: the live demo uses a weather service’s forecast for the site, and the benchmark uses four recorded weeks of Delhi weather together with the day-ahead forecasts that were actually issued. Demand is a simulated daily profile, because we don’t have smart-meter data yet. Every assumption is listed in the project README.' },
  { q: 'Why an optimizer and an AI?', a: 'Deciding how many kilowatts go where, hour by hour, is arithmetic, and an optimizer does it exactly and instantly. Language is where AI is strong: it reads what an operator writes, like “kal shaam 7 se 10 bijli jayegi”, turns it into a checked constraint for the optimizer, and shows what it understood before anything changes. You can also switch the AI on to decide, and compare.' },
  { q: 'How is it better than today’s controllers?', a: normal
      ? `A fixed-rule controller uses solar, then battery, then grid. On four recorded weeks of Delhi weather, with the same conditions and safety rules for both, the optimizer ran about ${normal.cost_reduction_pct.toFixed(0)}% cheaper with the grid normal${cuts ? `, and about ${cuts.cost_reduction_pct.toFixed(0)}% cheaper with a daily 3-hour evening power cut, using ${cuts.diesel_l.optimizer.toFixed(0)} litres of diesel instead of ${cuts.diesel_l.fixed.toFixed(0)}` : ''}. These are simulation results with stated assumptions, not field measurements.`
      : 'A fixed-rule controller uses solar, then battery, then grid. Surya Saarthi plans 24 hours ahead with prices, forecasts and power cuts; a fixed-rule controller runs on the same inputs, so the difference is measured, not claimed.' },
  { q: 'What if a decision is wrong?', a: 'It can’t act on it. Every decision, from the optimizer or the AI, passes through hard safety rules afterwards: the battery never goes below 20% or past the battery management system’s limits, essential loads are always powered and flexible jobs always finish before their deadline. When a rule steps in, the dashboard shows it.' },
  { q: 'Does it need the internet?', a: 'The live weather and the AI need it; the optimizer runs on the server. A site controller can download a signed 24-hour plan and keep following it, with its own safety rules, if the connection drops; if the plan is stale it falls back to the fixed rule.' },
  { q: 'What would it cost to use?', a: 'It is software only, built with free and open-source tools, and runs on a small server. It needs no new panels or batteries; a real site would add a link to its inverter or smart meter.' },
  { q: 'Can it control real equipment?', a: 'Not yet. Today it runs as a simulation. The signed 24-hour plan is the interface a real inverter or site controller would use, with the same safety rules in front of it.' },
]

export default function Landing({ onStart }) {
  const reducedMotion = usePrefersReducedMotion()
  const [webgl] = useState(hasWebGL)   // the hero background needs WebGL; without it, skip it
  useEffect(() => { document.title = `${PRODUCT_NAME} — AI for solar microgrids` }, [])
  // A normal #anchor would change the route, so skip-to-content moves focus directly.
  const skipToContent = (e) => { e.preventDefault(); document.getElementById('content')?.focus() }

  return (
    <div className="min-h-screen animate-in fade-in duration-500">
      <a href="#content" onClick={skipToContent} className="skip-link">Skip to content</a>
      <nav className="sticky top-0 z-20 flex items-center justify-between px-6 sm:px-14 py-5 border-b border-border bg-background/85 backdrop-blur-sm">
        <span className="flex items-center gap-2.5 font-display font-semibold">
          <span className="h-2 w-2 rounded-full bg-battery" />
          {PRODUCT_NAME}
        </span>
        <div className="flex items-center gap-2">
          <Button variant="ghost" size="sm" nativeButton={false}
                  render={<a href={REPO_URL} target="_blank" rel="noreferrer" />}>GitHub</Button>
          <Button variant="outline" size="sm" onClick={onStart}>Open dashboard</Button>
        </div>
      </nav>

      <section className="landing-hero">
        {!reducedMotion && webgl && (
          <FallbackBoundary>
            <Suspense fallback={null}><WebGLShader className="opacity-60 pointer-events-none" /></Suspense>
          </FallbackBoundary>
        )}
        <div className="hero-fade" />

        <Badge variant="outline" className="relative z-10 mb-5 font-mono text-[0.7rem] tracking-wider text-battery border-battery/30 uppercase">
          {PRODUCT_NAME} · AI for solar microgrids
        </Badge>
        <h1 className="relative z-10 font-display font-semibold text-[clamp(2.2rem,5.5vw,4.2rem)] leading-[1.08] tracking-tight max-w-3xl mb-5">
          The sun doesn't send an invoice.<br />Many microgrids waste it anyway.
        </h1>
        <p className="relative z-10 text-muted-foreground text-[clamp(1rem,1.5vw,1.2rem)] leading-relaxed max-w-xl mb-9">
          Plans every hour of solar, battery, grid and diesel together — saving sunshine for the
          evening peak and for power cuts, moving flexible jobs to cheaper hours, burning less diesel —
          and explains each decision in English or Hindi.
        </p>
        <LiquidButton size="xl" onClick={onStart} className="relative z-10">See it decide →</LiquidButton>

        <div className="scroll-cue relative z-10" aria-hidden="true"><span />Scroll</div>
      </section>

      <div id="content" tabIndex={-1} className="outline-none" />
      <ResultsStrip />

      <section className="landing-section">
        <Reveal><span className="section-eyebrow">The problem</span></Reveal>
        <Reveal delay={80}>
          <h2>Many rooftop and campus solar systems fall back to the grid the moment a cloud rolls in — not because there's no better option, but because nothing is watching closely enough to find one.</h2>
        </Reveal>
        <Reveal delay={140} className="landing-text">
          <p>India's decentralized solar push — PM Surya Ghar Muft Bijli Yojana rooftops, campus
            microgrids, community batteries — is growing fast on hardware. The software controlling it
            is often still a fixed threshold: pull from grid below a fixed battery percentage, no
            matter what the weather is about to do, no matter what's actually plugged in.</p>
          <p>And since the 2023 Time-of-Day tariff rules, <em>when</em> you use power matters: at least
            20% cheaper during solar hours, and 10–20% costlier at the evening peak (set by each
            state; we assume 20%). A fixed rule can't take advantage of that. {PRODUCT_NAME} can.</p>
          <p>Where the grid goes out, it matters even more. A battery that a fixed rule drained at
            6 pm is empty when the evening power cut starts, so the diesel genset runs instead.
            Told about the cut in advance, {PRODUCT_NAME} fills the battery first.</p>
        </Reveal>
      </section>

      <section className="landing-section">
        <Reveal><span className="section-eyebrow">How it decides</span></Reveal>
        <div className="stages-list">
          {STAGES.map((s, i) => (
            <Reveal key={s.name} delay={i * 60} className="stage-row">
              <span className="stage-index font-mono">0{i + 1}</span>
              <div>
                <h3 className="font-display">{s.name}</h3>
                <p>{s.desc}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      <section className="landing-section">
        <Reveal><span className="section-eyebrow">What it manages</span></Reveal>
        <Reveal delay={80}><h2>Six things, decided together every hour.</h2></Reveal>
        <div className="card-grid six">
          {MANAGES.map((m, i) => (
            <Reveal key={m.name} delay={120 + i * 50} className="info-card">
              <m.icon className={`h-6 w-6 ${m.color}`} aria-hidden="true" />
              <h3 className="font-display">{m.name}</h3>
              <p>{m.desc}</p>
            </Reveal>
          ))}
        </div>
      </section>

      <section className="landing-section">
        <Reveal><span className="section-eyebrow">Who it's for</span></Reveal>
        <Reveal delay={80}><h2>Wherever solar and a battery have to keep the lights on.</h2></Reveal>
        <div className="card-grid three">
          {AUDIENCE.map((a, i) => (
            <Reveal key={a.name} delay={120 + i * 60} className="info-card">
              <a.icon className="h-6 w-6 text-battery" aria-hidden="true" />
              <h3 className="font-display">{a.name}</h3>
              <p>{a.desc}</p>
            </Reveal>
          ))}
        </div>
      </section>

      <section className="landing-section statement-section">
        <Reveal><h2 className="statement">It plans. It explains. It cannot override the safety rules.</h2></Reveal>
        <Reveal delay={100} className="landing-text">
          <p>An optimizer does the arithmetic: the next 24 hours of sun, prices, jobs and power cuts,
            planned again every hour. The AI does the language: it reads the operator's notes into
            checked constraints, and can take over deciding when you want to compare. Neither gets
            the final word. Fixed rules check every decision afterwards, together with the battery
            management system's live limits, and step in if the battery would drop below its reserve
            or a load would go unmet.</p>
        </Reveal>
      </section>

      <section className="landing-section">
        <Reveal><span className="section-eyebrow">FAQs</span></Reveal>
        <div className="faq-list">
          {FAQ.map((item) => (
            <details key={item.q} className="faq-item">
              <summary className="font-display">{item.q}</summary>
              <p>{item.a}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="landing-section cta-section">
        {!reducedMotion && (
          <Suspense fallback={null}>
            <Waves className="absolute inset-0" strokeColor="#4fd8c4" backgroundColor="transparent" pointerSize={0.4} />
          </Suspense>
        )}
        <div className="relative z-10 cta-panel">
          <Reveal><span className="section-eyebrow">Live demo</span></Reveal>
          <Reveal delay={80}><h2>Run it yourself. Watch the battery, the grid, and the reasoning change in real time.</h2></Reveal>
          <Reveal delay={160}><LiquidButton size="xl" onClick={onStart} className="mt-8">Start live session →</LiquidButton></Reveal>
        </div>
      </section>

      <footer className="landing-footer">
        <span className="block font-display text-sm text-foreground">{PRODUCT_NAME}</span>
        <span className="block mt-1">{TAGLINE}</span>
        <span className="block mt-3">Smart India Hackathon 2026 · {SIH_PS_ID} · {SIH_PS_TITLE}{TEAM_NAME ? ` · Team ${TEAM_NAME}` : ''}</span>
        <span className="block mt-2">SDG 7 · Affordable &amp; Clean Energy</span>
        <nav className="footer-links" aria-label="Footer">
          <a href="https://open-meteo.com/" target="_blank" rel="noreferrer">Weather data by Open-Meteo.com</a>
          <a href={REPO_URL} target="_blank" rel="noreferrer">Source on GitHub</a>
          <a href="#/privacy">Privacy &amp; Disclaimer</a>
          <a href="#/credits">Credits &amp; licences</a>
        </nav>
      </footer>
    </div>
  )
}