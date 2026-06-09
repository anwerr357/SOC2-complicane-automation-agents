import { NavLink } from 'react-router-dom'

const NAV = [
  { to: '/',            label: 'Overview',   icon: '▦' },
  { to: '/violations',  label: 'Violations', icon: '⚑' },
]

export default function Sidebar() {
  return (
    <aside className="flex h-screen w-56 flex-col border-r border-gray-200 bg-white">
      <div className="flex h-16 items-center border-b border-gray-200 px-6">
        <span className="text-sm font-semibold text-gray-900">SOC 2 Compliance</span>
      </div>

      <nav className="flex-1 overflow-y-auto px-3 py-4" aria-label="Main navigation">
        {NAV.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors focus-visible:ring-2 focus-visible:ring-primary ${
                isActive
                  ? 'bg-blue-50 text-blue-600'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-900'
              }`
            }
          >
            <span aria-hidden="true">{icon}</span>
            {label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-gray-200 px-6 py-4">
        <p className="text-xs text-gray-400">Auto-refreshes every 30s</p>
      </div>
    </aside>
  )
}
