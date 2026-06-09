interface Props {
  label: string
  value: number
  accent?: 'default' | 'danger' | 'success' | 'warning'
}

const ACCENT: Record<NonNullable<Props['accent']>, string> = {
  default: 'text-gray-900',
  danger:  'text-red-600',
  success: 'text-green-600',
  warning: 'text-amber-600',
}

export default function MetricCard({ label, value, accent = 'default' }: Props) {
  return (
    <div className="rounded-xl bg-white p-6 shadow-sm ring-1 ring-gray-200">
      <p className="text-sm font-medium text-gray-500">{label}</p>
      <p className={`mt-2 text-4xl font-bold tabular-nums ${ACCENT[accent]}`}>
        {value.toLocaleString()}
      </p>
    </div>
  )
}
