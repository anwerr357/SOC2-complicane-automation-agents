import type { EventStatus } from '../../types/evidence'

const STYLES: Record<EventStatus, string> = {
  open:           'bg-red-50 text-red-700 ring-1 ring-red-200',
  remediated:     'bg-green-50 text-green-700 ring-1 ring-green-200',
  escalated:      'bg-amber-50 text-amber-700 ring-1 ring-amber-200',
  false_positive: 'bg-gray-100 text-gray-500 ring-1 ring-gray-200',
}

const LABELS: Record<EventStatus, string> = {
  open:           'Open',
  remediated:     'Remediated',
  escalated:      'Escalated',
  false_positive: 'False positive',
}

interface Props {
  status: EventStatus
}

export default function StatusBadge({ status }: Props) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${STYLES[status]}`}
      aria-label={`status: ${status}`}
    >
      {LABELS[status]}
    </span>
  )
}
