import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Brain, CheckSquare, Clock, AlertTriangle } from 'lucide-react';
import { api, type Memory, type Task } from '../lib/api';

export function Dashboard() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [overdueTasks, setOverdueTasks] = useState<Task[]>([]);
  const [dueSoonTasks, setDueSoonTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    async function loadData() {
      try {
        const [memoriesData, tasksData, overdueData, dueSoonData] = await Promise.all([
          api.getMemories(5),
          api.getTasks('pending', 5),
          api.getOverdueTasks(),
          api.getTasksDueSoon(24),
        ]);
        setMemories(memoriesData);
        setTasks(tasksData);
        setOverdueTasks(overdueData);
        setDueSoonTasks(dueSoonData);
      } catch (err) {
        console.error('Failed to load dashboard data:', err);
      } finally {
        setLoading(false);
      }
    }
    loadData();
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl md:text-3xl font-bold text-white">Welcome back, Nate</h1>
        <p className="text-slate-400 mt-1 text-sm md:text-base">Here's what's happening today.</p>
      </div>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4">
        <StatCard
          icon={Brain}
          label="Memories"
          value={memories.length}
          color="blue"
        />
        <StatCard
          icon={CheckSquare}
          label="Tasks"
          value={tasks.length}
          color="green"
        />
        <StatCard
          icon={AlertTriangle}
          label="Overdue"
          value={overdueTasks.length}
          color={overdueTasks.length > 0 ? 'red' : 'slate'}
        />
        <StatCard
          icon={Clock}
          label="Due Soon"
          value={dueSoonTasks.length}
          color={dueSoonTasks.length > 0 ? 'yellow' : 'slate'}
        />
      </div>

      {overdueTasks.length > 0 && (
        <div className="bg-red-900/30 border border-red-700 rounded-xl p-4">
          <h2 className="text-base font-semibold text-red-300 flex items-center gap-2">
            <AlertTriangle className="w-4 h-4" />
            Overdue Tasks
          </h2>
          <ul className="mt-3 space-y-2">
            {overdueTasks.slice(0, 3).map((task) => (
              <li key={task.id} className="p-3 bg-red-900/50 rounded-lg">
                <p className="text-red-200 text-sm">{task.title}</p>
                {task.due_at && (
                  <p className="text-red-400 text-xs mt-1">
                    Was due: {new Date(task.due_at).toLocaleDateString()}
                  </p>
                )}
              </li>
            ))}
          </ul>
          {overdueTasks.length > 3 && (
            <Link to="/tasks" className="text-red-400 text-sm mt-3 inline-block hover:underline">
              +{overdueTasks.length - 3} more
            </Link>
          )}
        </div>
      )}

      <div className="space-y-6 md:grid md:grid-cols-2 md:gap-6 md:space-y-0">
        <div className="bg-slate-900 rounded-xl p-4 md:p-6 border border-slate-700">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Recent Memories</h2>
            <Link to="/memories" className="text-blue-400 text-sm hover:underline">
              View all
            </Link>
          </div>
          {memories.length === 0 ? (
            <p className="text-slate-400 text-sm">No memories yet.</p>
          ) : (
            <ul className="space-y-3">
              {memories.map((memory) => (
                <li key={memory.id} className="p-3 bg-slate-800 rounded-lg">
                  <p className="text-slate-200 text-sm line-clamp-2">{memory.content}</p>
                  <p className="text-slate-500 text-xs mt-1">
                    {new Date(memory.created_at).toLocaleDateString()}
                  </p>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="bg-slate-900 rounded-xl p-4 md:p-6 border border-slate-700">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">Pending Tasks</h2>
            <Link to="/tasks" className="text-blue-400 text-sm hover:underline">
              View all
            </Link>
          </div>
          {tasks.length === 0 ? (
            <p className="text-slate-400 text-sm">No pending tasks.</p>
          ) : (
            <ul className="space-y-3">
              {tasks.map((task) => (
                <li key={task.id} className="p-3 bg-slate-800 rounded-lg">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="text-slate-200 font-medium text-sm truncate">{task.title}</p>
                      {task.due_at && (
                        <p className="text-slate-500 text-xs mt-1">
                          Due: {new Date(task.due_at).toLocaleDateString()}
                        </p>
                      )}
                    </div>
                    <PriorityBadge priority={task.priority} />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}

function StatCard({ icon: Icon, label, value, color }: {
  icon: typeof Brain;
  label: string;
  value: number | string;
  color: string;
}) {
  const colorClasses: Record<string, string> = {
    blue: 'bg-blue-900/50 border-blue-700 text-blue-400',
    green: 'bg-green-900/50 border-green-700 text-green-400',
    red: 'bg-red-900/50 border-red-700 text-red-400',
    yellow: 'bg-yellow-900/50 border-yellow-700 text-yellow-400',
    slate: 'bg-slate-900/50 border-slate-700 text-slate-400',
  };

  return (
    <div className={`rounded-xl p-3 md:p-4 border ${colorClasses[color]}`}>
      <div className="flex items-center justify-between">
        <Icon className="w-5 h-5 md:w-6 md:h-6" />
        <span className="text-xl md:text-2xl font-bold">{value}</span>
      </div>
      <p className="text-xs md:text-sm mt-2 opacity-80">{label}</p>
    </div>
  );
}

function PriorityBadge({ priority }: { priority: string }) {
  const colors: Record<string, string> = {
    low: 'bg-slate-600 text-slate-200',
    medium: 'bg-blue-600 text-blue-100',
    high: 'bg-orange-600 text-orange-100',
    urgent: 'bg-red-600 text-red-100',
  };

  return (
    <span className={`px-2 py-0.5 text-xs rounded flex-shrink-0 ${colors[priority] || colors.medium}`}>
      {priority}
    </span>
  );
}
