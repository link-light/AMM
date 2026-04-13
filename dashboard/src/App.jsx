import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Overview from './pages/Overview'
import Signals from './pages/Signals'
import Tasks from './pages/Tasks'
import HumanTasks from './pages/HumanTasks'
import CostDashboard from './pages/CostDashboard'
import Settings from './pages/Settings'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Overview />} />
        <Route path="signals" element={<Signals />} />
        <Route path="tasks" element={<Tasks />} />
        <Route path="human-tasks" element={<HumanTasks />} />
        <Route path="costs" element={<CostDashboard />} />
        <Route path="settings" element={<Settings />} />
      </Route>
    </Routes>
  )
}

export default App
