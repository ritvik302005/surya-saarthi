const STEPS = ['Sense', 'Decide', 'Safety check', 'Apply', 'Report']

export default function PipelineStepper({ stepIndex, replanFlash }) {
  return (
    <div className="stepper" role="list" aria-label="Agent pipeline stage">
      {STEPS.map((label, i) => {
        const state = i < stepIndex ? 'done' : i === stepIndex ? 'active' : 'pending'
        return (
          <div key={label} className="step" data-state={state}>
            <span className="step-dot" />
            <span className="step-label">{label}</span>
            {label === 'Decide' && replanFlash && <span className="step-loop">forecast missed: cautious</span>}
            {i < STEPS.length - 1 && <span className="step-line" />}
          </div>
        )
      })}
    </div>
  )
}
