import { lazy, Suspense, useState } from 'react'
import Landing from './Landing.jsx'

const Dashboard = lazy(() => import('./Dashboard.jsx'))

export default function App() {
  const [view, setView] = useState('landing')

  return view === 'landing' ? (
    <Landing onStart={() => setView('dashboard')} />
  ) : (
    <Suspense fallback={
      <div className="min-h-screen flex items-center justify-center gap-3 font-mono text-xs text-muted-foreground" role="status">
        <span className="h-2 w-2 rounded-full bg-battery animate-pulse" />Loading dashboard…
      </div>
    }>
      <Dashboard onBack={() => setView('landing')} />
    </Suspense>
  )
}