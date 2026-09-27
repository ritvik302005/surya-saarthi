import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { LiquidButton } from '@/components/ui/liquid-glass-button'
import { Sun, BatteryCharging, UtilityPole, Droplets, CarFront, House, GraduationCap, Tractor } from 'lucide-react'
import ResultsStrip from './ResultsStrip.jsx'
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
  { name: 'Sense', desc: 'Pulls real solar irradiance for the site from a live weather API, plus an 8-hour forecast, and reads a simulated demand profile.' },
  { name: 'Allocate', desc: "An LLM weighs solar, battery, grid and time-of-day prices, decides what to store, export or defer, and explains why." },
  { name: 'Safety limits', desc: "A hard, non-negotiable rule check — the model's suggestion can be overridden, never the reserve floor." },
  { name: 'Apply', desc: "Battery charge updates for real, and this cycle's forecast is compared against what was actually predicted." },
  { name: 'Replan', desc: 'If the forecast was wrong by enough to matter, it loops back and decides again, more conservatively.' },
  { name: 'Report', desc: 'Savings and carbon avoided are computed against a grid-only baseline, and compared live with a fixed-rule controller.' },
]

const MANAGES = [
  { icon: Sun, name: 'Solar panels', desc: 'Uses sunshine first, and knows the next 8 hours of forecast.', color: 'text-solar' },
  { icon: BatteryCharging, name: 'Battery', desc: 'Stores cheap daytime sun for the costly evening peak. Never below 20%.', color: 'text-battery' },
  { icon: UtilityPole, name: 'Grid', desc: 'Buys only what solar and battery can\u2019t cover; exports the rest under net metering.', color: 'text-grid' },
  { icon: Droplets, name: 'Water pump', desc: 'A flexible job: waits for sunshine, but always runs before its deadline.', color: 'text-battery' },
  { icon: CarFront, name: 'EV charging', desc: 'Moved out of the peak-price hours, finished by morning.', color: 'text-solar' },
]

const AUDIENCE = [
  { icon: House, name: 'Rooftop solar homes', desc: 'Households with solar and a battery under PM Surya Ghar Muft Bijli Yojana: lower bills without micromanaging.' },
  { icon: GraduationCap, name: 'Colleges and campuses', desc: 'Get more from solar already installed: cut peak-hour costs and schedule pumps and EV charging.' },
  { icon: Tractor, name: 'Village and farm microgrids', desc: 'Keep essential supply reliable and run solar pumps on sunshine instead of peak-price grid power.' },
]

const FAQ = [
  { q: 'Is this running on real data?', a: 'Sunlight comes from a live weather API (Open-Meteo) for the site, with an 8-hour forecast. Demand is a simulated daily profile of a home or small campus, because we don\u2019t have smart-meter data yet. Every assumption is listed in the project README.' },
  { q: 'What if the AI makes a wrong decision?', a: 'It can\u2019t act on it. Every decision passes through hard safety rules afterwards: the battery never goes below 20%, charge and discharge stay under 5 kW, essential loads are always powered and flexible jobs always finish before their deadline. When a rule steps in, the dashboard shows it.' },
  { q: 'Does it need the internet?', a: 'The AI planner and live weather use the internet. If either is unavailable, a fixed safe allocation takes over for that hour, so power is never left undecided.' },
  { q: 'How is it better than today\u2019s controllers?', a: 'A normal controller follows one rule: solar, then battery, then grid. Surya Saarthi also looks at time-of-day prices and the weather forecast, saves battery for the costly evening peak and moves pumps and EV charging to cheaper hours. A fixed-rule controller runs on the same inputs every hour, so the difference is measured, not claimed.' },
  { q: 'What would it cost to use?', a: 'It is software only, built with free and open-source tools, and runs on a small server. It needs no new panels or batteries; a real site would add a link to its inverter or smart meter.' },
  { q: 'Can it control real equipment?', a: 'Not yet. Today it runs as a simulation. The design keeps a clear place to connect an inverter or smart meter later, with the same safety rules in front of it.' },
]

export default function Landing({ onStart }) {
  const reducedMotion = usePrefersReducedMotion()
  useEffect(() => { document.title = `${PRODUCT_NAME} — AI for solar microgrids` }, [])

  return (
    <div className="min-h-screen animate-in fade-in duration-500">
      <a href="#content" className="skip-link">Skip to content</a>
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
        {!reducedMotion && <Suspense fallback={null}><WebGLShader className="opacity-60 pointer-events-none" /></Suspense>}
        <div className="hero-fade" />

        <Badge variant="outline" className="relative z-10 mb-5 font-mono text-[0.7rem] tracking-wider text-battery border-battery/30 uppercase">
          {PRODUCT_NAME} · AI for solar microgrids
        </Badge>
        <h1 className="relative z-10 font-display font-semibold text-[clamp(2.2rem,5.5vw,4.2rem)] leading-[1.08] tracking-tight max-w-3xl mb-5">
          The sun doesn't send an invoice.<br />Many microgrids waste it anyway.
        </h1>
        <p className="relative z-10 text-muted-foreground text-[clamp(1rem,1.5vw,1.2rem)] leading-relaxed max-w-xl mb-9">
          An AI agent that decides every hour whether to use solar, battery or grid power — storing
          sunshine for the evening peak, exporting the rest, moving flexible jobs to cheaper hours —
          and replanning when its own forecast turns out wrong.
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
        <Reveal delay={80}><h2>Five things, decided together every hour.</h2></Reveal>
        <div className="card-grid five">
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
        <Reveal delay={80}><h2>Anywhere solar and a battery share a roof with the grid.</h2></Reveal>
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
        <Reveal><h2 className="statement">It can reason. It cannot override a 20% reserve.</h2></Reveal>
        <Reveal delay={100} className="landing-text">
          <p>The allocation decision comes from a language model — genuinely useful for weighing
            solar against battery against grid, and for explaining its own reasoning in plain
            language. But it never gets the final word on safety. A fixed, deterministic rule
            checks every decision afterward and corrects it if the battery would drop below reserve
            or a load would go unmet. The model suggests; the rules decide.</p>
        </Reveal>
      </section>

      <section className="landing-section">
        <Reveal><span className="section-eyebrow">Questions judges ask</span></Reveal>
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