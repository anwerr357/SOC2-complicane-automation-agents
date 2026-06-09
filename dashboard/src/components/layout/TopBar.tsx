interface Props {
  title: string
  subtitle?: string
}

export default function TopBar({ title, subtitle }: Props) {
  return (
    <header className="flex h-16 items-center border-b border-gray-200 bg-white px-8">
      <div>
        <h1 className="text-base font-semibold text-gray-900">{title}</h1>
        {subtitle ? <p className="text-xs text-gray-500">{subtitle}</p> : null}
      </div>
    </header>
  )
}
