import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { LiquidButton } from '@/components/ui/liquid-glass-button'
import './Landing.css'

// The animated backgrounds pull in three.js and simplex-noise; load them after
// the page is up so the first paint doesn't wait on ~500 KB of decoration.
const WebGLShader = lazy(() => import('@/components/ui/web-gl-shader').then((m) => ({ default: m.WebGLShader })))
const Waves = lazy(() => import('@/components/ui/wave-background').then((m) => ({ default: m.Waves })))
const REPO_URL = 'https://github.com/ritvik302005/microgrid-agent'

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

export default function Landing({ onStart }) {
  const reducedMotion = usePrefersReducedMotion()

  return (
    <div className="min-h-screen animate-in fade-in duration-500">
      <nav className="sticky top-0 z-20 flex items-center justify-between px-6 sm:px-14 py-5 border-b border-border bg-background/85 backdrop-blur-sm">
        <span className="flex items-center gap-2.5 font-display font-semibold">
          <span className="h-2 w-2 rounded-full bg-battery" />
          Microgrid Control
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
          SDG 7 · Affordable &amp; Clean Energy
        </Badge>
        <h1 className="relative z-10 font-display font-semibold text-[clamp(2.2rem,5.5vw,4.2rem)] leading-[1.08] tracking-tight max-w-3xl mb-5">
          The sun doesn't send an invoice.<br />Most microgrids waste it anyway.
        </h1>
        <p className="relative z-10 text-muted-foreground text-[clamp(1rem,1.5vw,1.2rem)] leading-relaxed max-w-xl mb-9">
          An AI agent that decides every hour whether to use solar, battery or grid power — storing
          sunshine for the evening peak, exporting the rest, moving flexible jobs to cheaper hours —
          and replanning when its own forecast turns out wrong.
        </p>
        <LiquidButton size="xl" onClick={onStart} className="relative z-10">See it decide →</LiquidButton>

        <div className="scroll-cue relative z-10" aria-hidden="true"><span />Scroll</div>
      </section>

      <section className="landing-section">
        <Reveal><span className="section-eyebrow">The problem</span></Reveal>
        <Reveal delay={80}>
          <h2>Most rooftop and campus solar falls back to the grid the moment a cloud rolls in — not because there's no better option, but because nothing is watching closely enough to find one.</h2>
        </Reveal>
        <Reveal delay={140} className="landing-text">
          <p>India's decentralized solar push — rooftop subsidies, campus microgrids, community
            batteries — is growing fast on hardware. The software controlling it is mostly still a
            fixed threshold: pull from grid below a fixed battery percentage, no matter what the
            weather is about to do, no matter what's actually plugged in.</p>
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

      <section className="landing-section statement-section">
        <Reveal><h2 className="statement">It can reason. It cannot override a 20% reserve.</h2></Reveal>
        <Reveal delay={100} className="landing-text">
          <p>The allocation decision comes from a language model — genuinely useful for weighing
            solar against battery against grid, and for explaining its own reasoning in plain
            language. But it never gets the final word on safety. A fixed, deterministic rule
            checks every decision afterward and corrects it if the battery would drop below reserve
            or a load would go unmet — the same reasoning-plus-hard-limits pattern used for
            safety-critical routing in hospitals and emergency systems.</p>
        </Reveal>
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
        <span>Sense → Allocate → Safety limits → Apply → Replan if needed → Report</span>
        <span className="block mt-2">SDG 7 · Affordable &amp; Clean Energy · <a href={REPO_URL} target="_blank" rel="noreferrer" className="underline underline-offset-4 hover:text-foreground">Source on GitHub</a></span>
      </footer>
    </div>
  )
}