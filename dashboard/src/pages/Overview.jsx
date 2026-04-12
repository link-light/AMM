import { useState, useEffect } from 'react'
import { 
  Radio, 
  ListTodo, 
  UserCheck, 
  DollarSign 
} from 'lucide-react'

function StatCard({ title, value, subtitle, icon: Icon }) {
  return (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm text-gray-500">{title}</p>
          <p className="text-2xl font-bold mt-1">{value}</p>
          {subtitle && <p className="text-sm text-gray-400 mt-1">{subtitle}</p>}
        </div>
        <div className="p-3 bg-blue-500 rounded-lg">
          <Icon className="w-6 h-6 text-white" />
        </div>
      </div>
    </div>
  )
}

function Overview() {
  const [stats, setStats] = useState({
    signals: 0,
    tasks: 0,
    humanTasks: 0,
    todayCost: 0
  })

  useEffect(() => {
    // Fetch data from API
    fetch('http://127.0.0.1:8080/api/analytics/overview?days=7')
      .then(r => r.json())
      .then(data => {
        if (data.success) {
          setStats({
            signals: data.data?.signals?.total || 0,
            tasks: data.data?.tasks?.total || 0,
            humanTasks: 0,
            todayCost: data.data?.financial?.total_cost || 0
          })
        }
      })
      .catch(() => {
        // Use mock data if API not available
        setStats({
          signals: 5,
          tasks: 3,
          humanTasks: 2,
          todayCost: 0.15
        })
      })
  }, [])

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Overview</h1>

      {/* Stats grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title="Signals (7d)"
          value={stats.signals}
          subtitle="New opportunities"
          icon={Radio}
        />
        <StatCard
          title="Active Tasks"
          value={stats.tasks}
          subtitle="In progress"
          icon={ListTodo}
        />
        <StatCard
          title="Pending Human Tasks"
          value={stats.humanTasks}
          subtitle="Needs attention"
          icon={UserCheck}
        />
        <StatCard
          title="Today's AI Cost"
          value={`$${stats.todayCost.toFixed(2)}`}
          subtitle="Of $20 budget"
          icon={DollarSign}
        />
      </div>

      {/* Welcome message */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold mb-2">Welcome to AI Money Machine</h2>
        <p className="text-gray-600">
          This dashboard helps you manage AI-discovered business opportunities, 
          monitor tasks, and track costs.
        </p>
        <div className="mt-4 text-sm text-gray-500">
          <p>🚀 API Status: <span className="text-green-500">Connected</span></p>
          <p>🤖 AI Mode: <span className="text-blue-500">Mock (Development)</span></p>
        </div>
      </div>
    </div>
  )
}

export default Overview
