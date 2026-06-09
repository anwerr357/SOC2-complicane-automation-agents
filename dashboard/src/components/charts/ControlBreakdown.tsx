import { useMemo } from 'react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import type { EvidenceEvent } from '../../types/evidence'

interface Props {
  events: EvidenceEvent[]
}

const STATUS_COLOR: Record<string, string> = {
  open:           '#DC2626',
  escalated:      '#D97706',
  remediated:     '#16A34A',
  false_positive: '#9CA3AF',
}

export default function ControlBreakdown({ events }: Props) {
  const data = useMemo(() => {
    const map = new Map<string, number>()
    for (const e of events) {
      map.set(e.control_id, (map.get(e.control_id) ?? 0) + 1)
    }
    return Array.from(map.entries())
      .sort(([, a], [, b]) => b - a)
      .slice(0, 10)
      .map(([control_id, count]) => ({ control_id, count }))
  }, [events])

  const statusData = useMemo(() => {
    const map = new Map<string, number>()
    for (const e of events) {
      map.set(e.status, (map.get(e.status) ?? 0) + 1)
    }
    return Array.from(map.entries()).map(([status, count]) => ({ status, count }))
  }, [events])

  if (data.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-gray-400">
        No data yet
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <ResponsiveContainer width="100%" height={200}>
        <BarChart data={data} margin={{ top: 4, right: 8, left: -24, bottom: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#F3F4F6" vertical={false} />
          <XAxis dataKey="control_id" tick={{ fontSize: 11, fill: '#6B7280' }} tickLine={false} axisLine={false} />
          <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: '#6B7280' }} tickLine={false} axisLine={false} />
          <Tooltip
            contentStyle={{ border: '1px solid #E5E7EB', borderRadius: 8, fontSize: 12 }}
            cursor={{ fill: '#F9FAFB' }}
          />
          <Bar dataKey="count" radius={[4, 4, 0, 0]} fill="#3B82F6" maxBarSize={40} />
        </BarChart>
      </ResponsiveContainer>

      <div className="flex flex-wrap gap-3">
        {statusData.map(({ status, count }) => (
          <div key={status} className="flex items-center gap-1.5 text-xs text-gray-600">
            <span
              className="inline-block h-2.5 w-2.5 rounded-full"
              style={{ background: STATUS_COLOR[status] ?? '#9CA3AF' }}
            />
            <span className="capitalize">{status.replace('_', ' ')}</span>
            <span className="font-semibold text-gray-900">{count}</span>
          </div>
        ))}
      </div>
    </div>
  )
}
