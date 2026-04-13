import { useState, useEffect } from 'react'
import { Check, X, Eye } from 'lucide-react'

function Signals() {
  const [signals, setSignals] = useState([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetchSignals()
  }, [])

  const fetchSignals = async () => {
    try {
      const res = await fetch('http://127.0.0.1:8080/api/signals')
      const data = await res.json()
      if (data.success) {
        setSignals(data.data?.items || [])
      }
    } catch (e) {
      // Mock data
      setSignals([
        { id: '1', title: 'Python Web Scraper', source: 'upwork', score: 75, status: 'accepted', estimated_revenue: 500 },
        { id: '2', title: 'API Integration', source: 'fiverr', score: 62, status: 'pending', estimated_revenue: 350 },
      ])
    }
    setLoading(false)
  }

  if (loading) return <div className="p-4">Loading...</div>

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Signals</h1>

      <div className="bg-white rounded-lg shadow overflow-hidden">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Source</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Title</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Revenue</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Score</th>
              <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase">Status</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {signals.map(signal => (
              <tr key={signal.id}>
                <td className="px-6 py-4">
                  <span className="px-2 py-1 bg-gray-100 rounded text-xs">{signal.source}</span>
                </td>
                <td className="px-6 py-4">{signal.title}</td>
                <td className="px-6 py-4">${signal.estimated_revenue}</td>
                <td className="px-6 py-4">
                  <span className={`font-medium ${signal.score >= 70 ? 'text-green-500' : 'text-yellow-500'}`}>
                    {signal.score}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <span className={`px-2 py-1 rounded text-xs ${
                    signal.status === 'accepted' ? 'bg-green-100 text-green-800' :
                    signal.status === 'rejected' ? 'bg-red-100 text-red-800' :
                    'bg-blue-100 text-blue-800'
                  }`}>
                    {signal.status}
                  </span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export default Signals
