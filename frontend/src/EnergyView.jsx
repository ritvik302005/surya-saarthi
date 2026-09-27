import { lazy, Suspense, useState } from 'react'
import EnergyFlow from './EnergyFlow.jsx'
import { FallbackBoundary, hasWebGL } from './webgl.jsx'

// The 3D scene (three.js) loads on demand; the flat diagram is the fallback while it
// loads, on devices without WebGL, and if the 3D scene fails for any reason.
const EnergyScene3D = lazy(() => import('./EnergyScene3D.jsx'))

export default function EnergyView(props) {
  const { solarKw = 0, batteryKw = 0, gridKw = 0, gensetKw = 0, unservedKw = 0, gridAvailable = true,
          criticalKw = 0, flexibleLoads = [], loading } = props
  const [use3d] = useState(hasWebGL)
  const loadKw = criticalKw + flexibleLoads.filter((l) => !l.deferred).reduce((s, l) => s + l.power_kw, 0)
  const deferred = flexibleLoads.filter((l) => l.deferred)
  const flat = <EnergyFlow {...props} showDeferred={false} />
  const summary = `Power right now: solar ${(props.solarGenKw ?? solarKw).toFixed(1)} kW generated, battery `
    + `${batteryKw < -0.05 ? 'charging' : 'supplying'} ${Math.abs(batteryKw).toFixed(1)} kW, `
    + (gridAvailable ? `grid ${gridKw.toFixed(1)} kW` : `power cut, genset ${gensetKw.toFixed(1)} kW`)
    + `, load ${loadKw.toFixed(1)} kW${unservedKw > 0.05 ? `, ${unservedKw.toFixed(1)} kW not served` : ''}.`

  return (
    <>
      <div role="img" aria-label={summary}>
        {use3d ? (
          <FallbackBoundary fallback={flat}>
            <Suspense fallback={flat}>
              <EnergyScene3D {...props} loadKw={loadKw} loading={loading} />
            </Suspense>
          </FallbackBoundary>
        ) : flat}
      </div>
      {deferred.length > 0 && (
        <div className="deferred-strip">
          <span className="deferred-label">Deferred this hour</span>
          {deferred.map((l) => (
            <span key={l.name} className="deferred-chip">{l.name.replace('_', ' ')} · until {l.deadline}</span>
          ))}
        </div>
      )}
    </>
  )
}
