import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import TopBar from '../components/layout/TopBar'
import StatusBadge from '../components/badges/StatusBadge'
import SeverityBadge from '../components/badges/SeverityBadge'
import { useEvidence } from '../hooks/useEvidence'
import type { AgentName, EventStatus, ScannerUsed, Severity } from '../types/evidence'

const ALL = 'all'

export default function Violations() {
  const { events, isLoading, error } = useEvidence()

  const [query,    setQuery]    = useState('')
  const [agent,    setAgent]    = useState<AgentName | 'all'>(ALL)
  const [scanner,  setScanner]  = useState<ScannerUsed | 'all'>(ALL)
  const [severity, setSeverity] = useState<Severity | 'all'>(ALL)
  const [statusF,  setStatusF]  = useState<EventStatus | 'all'>(ALL)

  const filtered = useMemo(() => {
    const q = query.toLowerCase()
    return events.filter((e) => {
      if (agent    !== ALL && e.agent_name   !== agent)    return false
      if (scanner  !== ALL && e.scanner_used !== scanner)  return false
      if (severity !== ALL && e.severity     !== severity) return false
      if (statusF  !== ALL && e.status       !== statusF)  return false
      if (q && !e.check_id.toLowerCase().includes(q) &&
               !e.control_id.toLowerCase().includes(q) &&
               !e.resource_name.toLowerCase().includes(q)) return false
      return true
    })
  }, [events, query, agent, scanner, severity, statusF])

  if (error) {
    return (
      <div className="flex flex-1 items-center justify-center text-sm text-red-600">
        Failed to load events — is the API running?
      </div>
    )
  }

  return (
    <div className="flex flex-1 flex-col overflow-y-auto">
      <TopBar title="Violations" subtitle={`${filtered.length} of ${events.length} events`} />

      <main className="flex-1 p-8">
        {/* ── Filters ─────────────────────────────────────────────── */}
        <div className="mb-6 flex flex-wrap items-center gap-3">
          <input
            type="search"
            placeholder="Search check, control, resource…"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="h-8 rounded-lg border border-gray-200 px-3 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-primary"
          />

          <Select label="Agent" value={agent} onChange={setAgent}>
            <option value={ALL}>All agents</option>
            <option value="policy">Policy</option>
            <option value="cluster_operator">Cluster operator</option>
            <option value="dev_team">Dev team</option>
          </Select>

          <Select label="Scanner" value={scanner} onChange={setScanner}>
            <option value={ALL}>All scanners</option>
            <option value="checkov">Checkov</option>
            <option value="trufflehog">Trufflehog</option>
            <option value="semgrep">Semgrep</option>
            <option value="k8s_watch">K8s watch</option>
            <option value="prometheus">Prometheus</option>
          </Select>

          <Select label="Severity" value={severity} onChange={setSeverity}>
            <option value={ALL}>All severities</option>
            <option value="HIGH">High</option>
            <option value="MEDIUM">Medium</option>
            <option value="LOW">Low</option>
            <option value="INFO">Info</option>
          </Select>

          <Select label="Status" value={statusF} onChange={setStatusF}>
            <option value={ALL}>All statuses</option>
            <option value="open">Open</option>
            <option value="remediated">Remediated</option>
            <option value="escalated">Escalated</option>
            <option value="false_positive">False positive</option>
          </Select>
        </div>

        {/* ── Table ───────────────────────────────────────────────── */}
        <div className="overflow-hidden rounded-xl bg-white shadow-sm ring-1 ring-gray-200">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50 text-left">
                <Th>Check</Th>
                <Th>Control</Th>
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
                  <td colSpan={7} className="py-12 text-center text-gray-400">Loading…</td>
                </tr>
              ) : filtered.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-gray-400">No violations match your filters.</td>
                </tr>
              ) : (
                filtered.map((e) => (
                  <tr key={e.id} className="border-b border-gray-50 hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-3">
                      <span className="font-mono text-xs text-gray-700">{e.check_id}</span>
                    </td>
                    <td className="px-4 py-3">
                      <Link
                        to={`/control/${e.control_id}`}
                        className="text-xs text-blue-600 hover:underline focus-visible:underline"
                      >
                        {e.control_id}
                      </Link>
                      <p className="text-xs text-gray-400 leading-tight">{e.control_name}</p>
                    </td>
                    <td className="max-w-[180px] truncate px-4 py-3 font-mono text-xs text-gray-600">
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
                          aria-label="Open pull request"
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

function Select<T extends string>({
  label,
  value,
  onChange,
  children,
}: {
  label: string
  value: T
  onChange: (v: T) => void
  children: React.ReactNode
}) {
  return (
    <select
      aria-label={label}
      value={value}
      onChange={(e) => onChange(e.target.value as T)}
      className="h-8 rounded-lg border border-gray-200 px-2 text-sm text-gray-700 focus:outline-none focus:ring-2 focus:ring-primary"
    >
      {children}
    </select>
  )
}
