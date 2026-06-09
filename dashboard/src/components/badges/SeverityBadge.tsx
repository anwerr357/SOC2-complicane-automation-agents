import type { Severity } from '../../types/evidence'

const STYLES: Record<Severity, string> = {
  HIGH:   'bg-red-100 text-red-700',
  MEDIUM: 'bg-amber-100 text-amber-700',
  LOW:    'bg-blue-100 text-blue-700',
  INFO:   'bg-gray-100 text-gray-500',
}

interface Props {
  severity: Severity
}

export default function SeverityBadge({ severity }: Props) {
  return (
    <span
      className={`inline-flex items-center rounded px-2 py-0.5 text-xs font-semibold font-mono ${STYLES[severity]}`}
      aria-label={`severity: ${severity}`}
    >
      {severity}
    </span>
  )
}
