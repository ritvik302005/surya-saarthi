import { lazy, Suspense, useEffect, useRef, useState } from 'react'
import Landing from './Landing.jsx'

const Dashboard = lazy(() => import('./Dashboard.jsx'))
const Privacy = lazy(() => import('./Privacy.jsx'))

// Only the info page has its own URL (#/privacy, #/credits) so it can be linked;
// landing and dashboard still switch by state.
const isInfoHash = () => ['#/privacy', '#/credits'].includes(window.location.hash)

const loadingScreen = (text) => (
  <div className="min-h-screen flex items-center justify-center gap-3 font-mono text-xs text-muted-foreground" role="status">
    <span className="h-2 w-2 rounded-full bg-battery animate-pulse" />{text}
  </div>
)

export default function App() {
  const [view, setView] = useState(() => (isInfoHash() ? 'privacy' : 'landing'))
  const viewRef = useRef(view)
  const returnTo = useRef(null)   // view to restore when leaving the info page; null = opened directly
  viewRef.current = view

  useEffect(() => {
    const onHashChange = () => {
      if (isInfoHash()) {
        if (viewRef.current !== 'privacy') { returnTo.current = viewRef.current; setView('privacy') }
      } else if (viewRef.current === 'privacy') {
        setView(returnTo.current || 'landing')
        returnTo.current = null
      }
    }
    window.addEventListener('hashchange', onHashChange)
    return () => window.removeEventListener('hashchange', onHashChange)
  }, [])

  // Opened from a footer link: step back so browser history stays tidy.
  const leaveInfo = () => (returnTo.current ? window.history.back() : (window.location.hash = ''))

  if (view === 'privacy') {
    return <Suspense fallback={loadingScreen('Loading…')}><Privacy onBack={leaveInfo} /></Suspense>
  }
  return view === 'landing' ? (
    <Landing onStart={() => setView('dashboard')} />
  ) : (
    <Suspense fallback={loadingScreen('Loading dashboard…')}>
      <Dashboard onBack={() => setView('landing')} />
    </Suspense>
  )
}
