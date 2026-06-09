import { lazy, Suspense, useMemo } from 'react'
import { useParams, Link } from 'react-router-dom'
import TopBar from '../components/layout/TopBar'
import StatusBadge from '../components/badges/StatusBadge'
import SeverityBadge from '../components/badges/SeverityBadge'
import MetricCard from '../components/cards/MetricCard'
import { useControlEvidence } from '../hooks/useEvidence'

const ControlBreakdown = lazy(() => import('../components/charts/ControlBreakdown'))

export default function ControlDetail() {
  const { controlId } = useParams<{ controlId: string }>()
  const { events, isLoading, error } = useControlEvidence(controlId ?? '')

  const counts = useMemo(() => ({
    total:      events.length,
    open:       events.filter((e) => e.status === 'open').length,
    remediated: events.filter((e) => e.status === 'remediated').length,
    escalated:  events.filter((e) => e.status === 'escalated').length,
  }), [events])

  const controlName = events[0]?.control_name ?? ''

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-red-600">
        Failed to load — is the API running?
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col overflow-y-auto">
      <TopBar
        title={controlId ?? ''}
        subtitle={controlName || 'SOC 2 control detail'}
      />

      <main className="flex-1 space-y-8 p-8">
        <Link to="/violations" className="text-xs text-blue-600 hover:underline">
          ← Back to all violations
        </Link>

        {isLoading ? (
          <div className="grid grid-cols-4 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="h-28 animate-pulse rounded-xl bg-gray-100" />
            ))}
          </div>
        ) : (
          <div className="grid grid-cols-4 gap-4">
            <MetricCard label="Total"       value={counts.total}      accent="default" />
            <MetricCard label="Open"        value={counts.open}       accent="danger"  />
            <MetricCard label="Remediated"  value={counts.remediated} accent="success" />
            <MetricCard label="Escalated"   value={counts.escalated}  accent="warning" />
          </div>
        )}

        <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
          <h2 className="mb-4 text-sm font-semibold text-gray-700">Scanner breakdown</h2>
          <Suspense fallback={<div className="h-48 animate-pulse rounded-lg bg-gray-100" />}>
            <ControlBreakdown events={events} />
          </Suspense>
        </div>

        <div className="overflow-hidden rounded-xl bg-white shadow-sm ring-1 ring-gray-200">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50 text-left">
                <Th>Check</Th>
                <Th>Resource</Th>
                <Th>Severity</Th>
                <Th>Status</Th>
                <Th>PR</Th>
                <Th>When</Th>
              </tr>
            </thead>
            <tbody>
              {isLoading ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-gray-400">Loading…</td>
                </tr>
              ) : events.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-12 text-center text-gray-400">
                    No violations for {controlId}.
                  </td>
                </tr>
              ) : (
                events.map((e) => (
                  <tr key={e.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3 font-mono text-xs text-gray-700">{e.check_id}</td>
                    <td className="max-w-[200px] truncate px-4 py-3 font-mono text-xs text-gray-600">
                      {e.resource_name}
                    </td>
                    <td className="px-4 py-3">
                      <SeverityBadge severity={e.severity} />
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={e.status} />
                    </td>
                    <td className="px-4 py-3">
                      {e.pr_url ? (
                        <a
                          href={e.pr_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-xs text-blue-600 hover:underline"
                        >
                          View PR ↗
                        </a>
                      ) : (
                        <span className="text-xs text-gray-300">—</span>
                      )}
                    </td>
                    <td className="px-4 py-3 text-xs text-gray-400">
                      {new Date(e.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </main>
    </div>
  )
}

function Th({ children }: { children: React.ReactNode }) {
  return (
    <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wide">
      {children}
    </th>
  )
}
