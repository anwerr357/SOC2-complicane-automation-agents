import { lazy, Suspense, useMemo } from 'react'
import TopBar from '../components/layout/TopBar'
import MetricCard from '../components/cards/MetricCard'
import { useEvidence } from '../hooks/useEvidence'

const TrendChart = lazy(() => import('../components/charts/TrendChart'))
const ControlBreakdown = lazy(() => import('../components/charts/ControlBreakdown'))

function ChartSkeleton() {
  return <div className="h-48 animate-pulse rounded-lg bg-gray-100" />
}

export default function Overview() {
  const { events, isLoading, error } = useEvidence()

  const counts = useMemo(() => ({
    total:      events.length,
    open:       events.filter((e) => e.status === 'open').length,
    remediated: events.filter((e) => e.status === 'remediated').length,
    escalated:  events.filter((e) => e.status === 'escalated').length,
  }), [events])

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-red-600">
        Failed to load events — is the API running?
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col overflow-y-auto">
      <TopBar title="Overview" subtitle="Last 200 events · auto-refreshes every 30 s" />

      <main className="flex-1 space-y-8 p-8">
        {isLoading ? (
          <div className="grid grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-28 animate-pulse rounded-xl bg-gray-100" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-4 gap-4">
            <MetricCard label="Total events"  value={counts.total}      accent="default" />
            <MetricCard label="Open"          value={counts.open}       accent="danger"  />
            <MetricCard label="Remediated"    value={counts.remediated} accent="success" />
            <MetricCard label="Escalated"     value={counts.escalated}  accent="warning" />
          </div>
        )}

        <div className="grid grid-cols-2 gap-6">
          <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
            <h2 className="mb-4 text-sm font-semibold text-gray-700">Violations over time (14 days)</h2>
            <Suspense fallback={<ChartSkeleton />}>
              <TrendChart events={events} />
            </Suspense>
          </div>

          <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
            <h2 className="mb-4 text-sm font-semibold text-gray-700">By SOC 2 control</h2>
            <Suspense fallback={<ChartSkeleton />}>
              <ControlBreakdown events={events} />
            </Suspense>
          </div>
        </div>
      </main>
    </div>
  )
}
