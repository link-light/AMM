import { useState, useEffect } from 'react'

function Tasks() {
  const [tasks, setTasks] = useState([])

  useEffect(() => {
    setTasks([
      { id: '1', title: 'Develop web scraper', status: 'running', task_type: 'coding' },
      { id: '2', title: 'Submit proposal', status: 'pending', task_type: 'human' },
      { id: '3', title: 'Code review', status: 'completed', task_type: 'review' },
    ])
  }, [])

  const statusColors = {
    pending: 'bg-gray-100',
    running: 'bg-yellow-100',
    completed: 'bg-green-100',
    failed: 'bg-red-100'
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Tasks</h1>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        {['pending', 'running', 'completed', 'failed'].map(status => (
          <div key={status}>
            <h3 className="font-medium capitalize mb-3">{status}</h3>
            <div className="space-y-3">
              {tasks.filter(t => t.status === status).map(task => (
                <div key={task.id} className="bg-white rounded-lg shadow p-4">
                  <p className="font-medium">{task.title}</p>
                  <span className={`inline-block mt-2 px-2 py-1 rounded text-xs ${statusColors[task.status]}`}>
                    {task.task_type}
                  </span>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default Tasks
