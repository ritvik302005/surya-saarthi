import { lazy, Suspense, useState } from 'react'
import Landing from './Landing.jsx'

const Dashboard = lazy(() => import('./Dashboard.jsx'))

export default function App() {
  const [view, setView] = useState('landing')

  return view === 'landing' ? (
    <Landing onStart={() => setView('dashboard')} />
  ) : (
    <Suspense fallback={null}>
      <Dashboard onBack={() => setView('landing')} />
    </Suspense>
  )
}