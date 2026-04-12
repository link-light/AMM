import { useState } from 'react'

function Settings() {
  const [config, setConfig] = useState({
    dailyLimit: 20,
    monthlyLimit: 400,
  })

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Settings</h1>

      <div className="bg-white rounded-lg shadow p-6 max-w-2xl">
        <h2 className="text-lg font-semibold mb-6">AI Gateway Configuration</h2>
        
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-2">
              Daily Budget Limit ($)
            </label>
            <input
              type="number"
              value={config.dailyLimit}
              onChange={(e) => setConfig({ ...config, dailyLimit: e.target.value })}
              className="w-full px-3 py-2 border rounded-lg"
            />
          </div>

          <div>
            <label className="block text-sm font-medium mb-2">
              Monthly Budget Limit ($)
            </label>
            <input
              type="number"
              value={config.monthlyLimit}
              onChange={(e) => setConfig({ ...config, monthlyLimit: e.target.value })}
              className="w-full px-3 py-2 border rounded-lg"
            />
          </div>
        </div>

        <div className="mt-6 pt-6 border-t">
          <button className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700">
            Save Changes
          </button>
        </div>
      </div>

      <div className="bg-white rounded-lg shadow p-6 max-w-2xl">
        <h2 className="text-lg font-semibold mb-4">System Information</h2>
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-500">Version</span>
            <span>0.1.0</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Environment</span>
            <span>Development</span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-500">Mock Mode</span>
            <span>Enabled</span>
          </div>
        </div>
      </div>
    </div>
  )
}

export default Settings
