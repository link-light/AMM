import { useState, useEffect } from 'react'

function HumanTasks() {
  const [tasks, setTasks] = useState([])

  useEffect(() => {
    setTasks([
      { id: '1', task_type: 'submit_proposal', platform: 'upwork', priority: 'high', instructions: 'Submit proposal for web scraper project' },
      { id: '2', task_type: 'deliver_work', platform: 'fiverr', priority: 'normal', instructions: 'Deliver completed API integration' },
    ])
  }, [])

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Human Tasks</h1>

      <div className="space-y-4">
        {tasks.map(task => (
          <div key={task.id} className="bg-white rounded-lg shadow p-4">
            <div className="flex justify-between items-start">
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium">{task.platform}</span>
                  <span className="text-gray-400">•</span>
                  <span className="text-sm">{task.task_type}</span>
                </div>
                <p className="mt-2 text-gray-600">{task.instructions}</p>
              </div>
              <span className={`px-2 py-1 rounded text-xs ${
                task.priority === 'high' ? 'bg-red-100 text-red-800' : 'bg-gray-100'
              }`}>
                {task.priority}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default HumanTasks
