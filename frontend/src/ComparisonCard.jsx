import { Card, CardTitle, CardDescription } from '@/components/ui/card'
import { PRODUCT_NAME } from './brand.js'

function Stat({ value, label, tone }) {
  return (
    <div>
      <span className={`block font-display text-2xl font-semibold ${tone || ''}`}>{value}</span>
      <span className="block text-xs text-muted-foreground mt-0.5">{label}</span>
    </div>
  )
}

function Bar({ label, kwh, max, className }) {
  const width = max > 0 ? Math.max(2, (kwh / max) * 100) : 0
  return (
    <div className="flex items-center gap-3 font-mono text-xs">
      <span className="w-28 shrink-0 text-muted-foreground">{label}</span>
      <div className="flex-1 h-2.5 rounded-full bg-secondary overflow-hidden">
        <div className={`h-full rounded-full ${className}`} style={{ width: `${width}%` }} />
      </div>
      <span className="w-20 text-right">{kwh.toFixed(1)} kWh</span>
    </div>
  )
}

export default function ComparisonCard({ comparison, csvUrl }) {
  if (!comparison || !comparison.hours) return null
  const c = comparison
  const better = c.grid_reduction_pct >= 0
  const max = Math.max(c.agent_grid_kwh, c.rule_grid_kwh)

  return (
    <section className="max-w-6xl mx-auto px-6 sm:px-9 mb-8">
      <Card className="p-8 gap-5">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <CardTitle className="font-mono text-xs tracking-wider uppercase text-muted-foreground font-normal mb-1.5">
              {PRODUCT_NAME} vs rule-based controller
            </CardTitle>
            <CardDescription>
              Same sunlight and demand, {c.hours} hour{c.hours !== 1 ? 's' : ''}. The rule-based controller uses solar,
              then battery, then grid, exports any surplus, and never shifts a load.
            </CardDescription>
          </div>
          <a href={csvUrl} className="font-mono text-xs underline underline-offset-4 text-muted-foreground hover:text-foreground">
            Download results (CSV)
          </a>
        </div>

        <div className="flex flex-col gap-2.5">
          <Bar label={PRODUCT_NAME} kwh={c.agent_grid_kwh} max={max} className="bg-battery" />
          <Bar label="Rule-based grid" kwh={c.rule_grid_kwh} max={max} className="bg-grid" />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-6">
          <Stat value={`${better ? '' : '+'}${Math.abs(c.grid_reduction_pct).toFixed(1)}%`}
                label={better ? 'less grid power than rule-based' : 'more grid power than rule-based'}
                tone={better ? 'text-battery' : 'text-grid'} />
          <Stat value={`₹${c.extra_savings_rs.toFixed(2)}`} label="saved vs rule-based (ToD tariff)" />
          <Stat value={`${c.renewable_share_pct.toFixed(1)}%`} label="demand met by solar + battery" />
          <Stat value={`${c.safety_override_hours} / ${c.ai_fallback_hours}`} label="hours with safety override / AI fallback" />
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-6 pt-5 border-t border-border">
          <Stat value={`${(c.solar_generated_kwh ?? 0).toFixed(1)} kWh`} label="solar generated" tone="text-solar" />
          <Stat value={`${(c.agent_solar_self_use_pct ?? 0).toFixed(1)}%`}
                label={`used on site or stored (rules: ${(c.rule_solar_self_use_pct ?? 0).toFixed(1)}%)`} />
          <Stat value={`${(c.agent_export_kwh ?? 0).toFixed(1)} kWh`} label="exported to grid (net metering)" />
          <Stat value={`${(c.solar_wasted_kwh ?? 0).toFixed(1)} kWh`} label="solar wasted" />
        </div>
      </Card>
    </section>
  )
}
