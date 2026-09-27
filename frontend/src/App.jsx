import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import Landing from './Landing.jsx'

const Dashboard = lazy(() => import('./Dashboard.jsx'))
const Privacy = lazy(() => import('./Privacy.jsx'))

// Each view has its own URL (#/dashboard, #/privacy, #/credits; landing has none), so
// links can be shared and the browser's Back button works. Skip links move focus
// instead of changing the hash, so any other hash means the landing page.
const ROUTES = { '#/dashboard': 'dashboard', '#/privacy': 'privacy', '#/credits': 'privacy' }
const viewFromHash = () => ROUTES[window.location.hash] || 'landing'

const loadingScreen = (text) => (
  <div className="min-h-screen flex items-center justify-center gap-3 font-mono text-xs text-muted-foreground" role="status">
    <span className="h-2 w-2 rounded-full bg-battery animate-pulse" />{text}
  </div>
)

export default function App() {
  const [view, setView] = useState(viewFromHash)
  const movedInApp = useRef(false)   // false while on the page the visitor opened, so Back would leave the site

  useEffect(() => {
    const onHashChange = () => {
      movedInApp.current = true
      setView(viewFromHash())
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  // Leaving the info page: step back if we came from inside the site, else go to the landing page.
  const leaveInfo = () => (movedInApp.current ? window.history.back() : (window.location.hash = ''))

  if (view === 'privacy') {
    return <Suspense fallback={loadingScreen('Loading…')}><Privacy onBack={leaveInfo} /></Suspense>
  }
  return view === 'landing' ? (
    <Landing onStart={() => { window.location.hash = '#/dashboard' }} />
  ) : (
    <Suspense fallback={loadingScreen('Loading dashboard…')}>
      <Dashboard onBack={() => { window.location.hash = '' }} />
    </Suspense>
  )
}
