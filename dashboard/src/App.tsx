import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Sidebar from './components/layout/Sidebar'
import Overview from './pages/Overview'
import Violations from './pages/Violations'
import ControlDetail from './pages/ControlDetail'

export default function App() {
  return (
    <BrowserRouter>
      <div className="flex h-screen overflow-hidden">
        <Sidebar />
        <div className="flex flex-1 flex-col overflow-hidden">
          <Routes>
            <Route path="/"                      element={<Overview />} />
            <Route path="/violations"             element={<Violations />} />
            <Route path="/control/:controlId"     element={<ControlDetail />} />
            <Route path="*"                       element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </div>
    </BrowserRouter>
  )
}
