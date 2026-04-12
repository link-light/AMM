import { useState, useEffect } from 'react'

function CostDashboard() {
  const [costs, setCosts] = useState({
    today: { spent: 0.15, limit: 20 },
    month: { spent: 1.25, limit: 400 }
  })

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Cost Dashboard</h1>

      {/* Budget cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-medium mb-4">Daily Budget</h3>
          <div className="w-full bg-gray-200 rounded-full h-2 mb-2">
            <div 
              className="bg-green-500 h-2 rounded-full"
              style={{ width: `${(costs.today.spent / costs.today.limit) * 100}%` }}
            />
          </div>
          <div className="flex justify-between text-sm">
            <span>${costs.today.spent.toFixed(2)}</span>
            <span className="text-gray-500">${costs.today.limit}</span>
          </div>
        </div>

        <div className="bg-white rounded-lg shadow p-6">
          <h3 className="text-lg font-medium mb-4">Monthly Budget</h3>
          <div className="w-full bg-gray-200 rounded-full h-2 mb-2">
            <div 
              className="bg-blue-500 h-2 rounded-full"
              style={{ width: `${(costs.month.spent / costs.month.limit) * 100}%` }}
            />
          </div>
          <div className="flex justify-between text-sm">
            <span>${costs.month.spent.toFixed(2)}</span>
            <span className="text-gray-500">${costs.month.limit}</span>
          </div>
        </div>
      </div>

      {/* Stats */}
      <div className="bg-white rounded-lg shadow p-6">
        <h3 className="text-lg font-medium mb-4">Cost Breakdown</h3>
        <div className="space-y-2">
          <div className="flex justify-between py-2 border-b">
            <span>Opus Tier</span>
            <span>$0.05</span>
          </div>
          <div className="flex justify-between py-2 border-b">
            <span>Sonnet Tier</span>
            <span>$0.08</span>
          </div>
          <div className="flex justify-between py-2 border-b">
            <span>Haiku Tier</span>
            <span>$0.02</span>
          </div>
        </div>
      </div>
    </div>
  )
}

export default CostDashboard
