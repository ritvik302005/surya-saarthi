import { useEffect, useRef } from 'react'
import { Button } from '@/components/ui/button'
import { PRODUCT_NAME, REPO_URL } from './brand.js'
import './Landing.css'

const UPDATED = '27 September 2026'

const ext = (href, text) => (
  <a href={href} target="_blank" rel="noreferrer" className="underline underline-offset-4 hover:text-foreground">{text}</a>
)

const CREDITS = [
  ['Weather data', <>{ext('https://open-meteo.com/', 'Weather data by Open-Meteo.com')}, licensed under {ext('https://creativecommons.org/licenses/by/4.0/', 'CC BY 4.0')}. Used through Open-Meteo’s free API, which is for non-commercial use.</>],
  ['CO₂ factor', <>CEA CO₂ Baseline Database for the Indian Power Sector, version 21.0 (Central Electricity Authority).</>],
  ['AI model', <>gpt-oss-20b by OpenAI (Apache 2.0), run on Groq.</>],
  ['Fonts', <>Space Grotesk, Inter and JetBrains Mono, all under the {ext('https://openfontlicense.org/', 'SIL Open Font License 1.1')}. Served from this site through Fontsource.</>],
  ['Icons', <>{ext('https://lucide.dev/license', 'Lucide')} (ISC licence).</>],
  ['Interface', <>React, Tailwind CSS, shadcn/ui, Base UI, Radix UI, three.js, simplex-noise, clsx and tailwind-merge (MIT); class-variance-authority (Apache 2.0).</>],
  ['Animated parts', <>
    Wave background by {ext('https://21st.dev/@xubohuah/components/wave-background', 'Kain Xu')}, inspired by Antoine Wodniack (MIT).
    WebGL shader and liquid glass button by {ext('https://21st.dev/@designali-in', 'Ali Imam')}, from 21st.dev, where no licence is stated.
    All three are adapted for this site.</>],
  ['Server', <>FastAPI, Pydantic, LangGraph and LangChain (MIT); Uvicorn and python-dotenv (BSD); Requests and the Groq SDK (Apache 2.0).</>],
]

export default function Privacy({ onBack }) {
  const mainRef = useRef(null)
  const creditsRef = useRef(null)

  useEffect(() => {
    document.title = `Privacy & Disclaimer · ${PRODUCT_NAME}`
    if (window.location.hash === '#/credits') creditsRef.current?.scrollIntoView()
    else window.scrollTo(0, 0)
  }, [])

  // A normal #anchor would change the route, so skip-to-content moves focus directly.
  const skip = (e) => { e.preventDefault(); mainRef.current?.focus() }

  return (
    <div className="min-h-screen flex flex-col animate-in fade-in duration-500">
      <a href="#info-main" onClick={skip} className="skip-link">Skip to content</a>
      <nav className="sticky top-0 z-20 flex items-center justify-between px-6 sm:px-14 py-5 border-b border-border bg-background/85 backdrop-blur-sm">
        <span className="flex items-center gap-2.5 font-display font-semibold">
          <span className="h-2 w-2 rounded-full bg-battery" />
          {PRODUCT_NAME}
        </span>
        <Button variant="outline" size="sm" onClick={onBack}>← Back</Button>
      </nav>

      <main id="info-main" ref={mainRef} tabIndex={-1} className="info-page outline-none">
        <span className="section-eyebrow">Last updated {UPDATED}</span>
        <h1 className="font-display">Privacy &amp; Disclaimer</h1>
        <p className="info-lead">
          {PRODUCT_NAME} is a demonstration built for Smart India Hackathon 2026. It asks you for
          nothing, and it keeps as little as it can. Here is exactly what happens.
        </p>

        <h2 className="font-display">What is stored</h2>
        <ul>
          <li><strong>In your browser:</strong> one random session ID, kept in session storage so a
            page refresh keeps your run. It is deleted when you close the tab. No cookies and no
            local storage are used.</li>
          <li><strong>On our server:</strong> your simulated run (hours, battery level, decisions),
            linked only to that random ID and kept in memory. Only the 100 most recent sessions are
            kept, and all of them are lost when the server restarts.</li>
          <li><strong>Server log:</strong> each simulated hour is also written to a log file on the
            server as numbers and the AI’s one-sentence reason. It contains no session ID and nothing
            about you.</li>
          <li>We never ask for your name, email, phone number or location. There are no accounts and
            nothing to type in.</li>
        </ul>

        <h2 className="font-display">What is sent where</h2>
        <ul>
          <li><strong>Your browser → our server (Render):</strong> the buttons you press (run an hour,
            simulate days, reset) and the session ID.</li>
          <li><strong>Our server → Groq (AI provider):</strong> the simulated numbers for each hour:
            sunlight, battery, demand, price and flexible jobs. Nothing about you is sent.</li>
          <li><strong>Our server → Open-Meteo:</strong> the fixed coordinates of the simulated site
            (Delhi), to get sunlight data. Never your location.</li>
          <li><strong>Hosting:</strong> like any website, our hosts (Vercel for this page, Render for the
            server) keep standard access logs such as IP address, browser type and time, for running
            and securing the service. We don’t use them to track anyone.</li>
          <li>Fonts, icons and code all load from this site. Nothing is loaded from Google or other
            third parties. The GitHub and credit links only open those sites if you click them.</li>
        </ul>

        <h2 className="font-display">No cookies, no tracking</h2>
        <p>No cookies, no analytics, no advertising, no tracking pixels and no fingerprinting.</p>

        <h2 className="font-display">This is a simulation</h2>
        <p>
          The microgrid, the household demand and the flexible jobs are simulated. Sunlight comes from
          a real weather forecast with random variation added. Tariffs, export credit and other values
          are assumptions, all listed in the {ext(`${REPO_URL}#assumptions`, 'project README')}.
          Savings shown are results of this simulation, not a promise of real savings.
        </p>
        <p>
          <strong>Do not use it to control real electrical equipment.</strong> The AI can make
          mistakes. The safety rules correct the simulation, but they have not been tested or
          certified for real hardware.
        </p>

        <h2 className="font-display">No warranty</h2>
        <p>
          This site and its code are provided “as is”, without warranty of any kind, express or
          implied, including fitness for a particular purpose. To the extent the law allows, the
          team is not liable for any loss or damage arising from using the site, its results or its
          code.
        </p>

        <h2 className="font-display" id="credits" ref={creditsRef}>Credits &amp; licences</h2>
        <dl className="credits-list">
          {CREDITS.map(([term, detail]) => (
            <div key={term}>
              <dt>{term}</dt>
              <dd>{detail}</dd>
            </div>
          ))}
        </dl>
        <p className="info-small">
          Full licence notices are in {ext(`${REPO_URL}/blob/main/THIRD_PARTY_NOTICES.md`, 'THIRD_PARTY_NOTICES.md')} in
          the source code.
        </p>
      </main>

      <footer className="landing-footer">
        <span className="block">{PRODUCT_NAME} · Smart India Hackathon 2026</span>
      </footer>
    </div>
  )
}
