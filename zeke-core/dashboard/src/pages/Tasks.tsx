import { useState, useEffect } from 'react';
import { Plus, Check, Trash2, CheckSquare, AlertTriangle, Clock, X } from 'lucide-react';
import { api, type Task } from '../lib/api';

export function Tasks() {
  const [tasks, setTasks] = useState<Task[]>([]);
  const [completedTasks, setCompletedTasks] = useState<Task[]>([]);
  const [overdueTasks, setOverdueTasks] = useState<Task[]>([]);
  const [dueSoonTasks, setDueSoonTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [showAddForm, setShowAddForm] = useState(false);
  const [showCompleted, setShowCompleted] = useState(false);
  const [newTask, setNewTask] = useState({ title: '', description: '', priority: 'medium' });
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    loadTasks();
  }, []);

  async function loadTasks() {
    try {
      const [pendingData, completedData, overdueData, dueSoonData] = await Promise.all([
        api.getTasks('pending', 50),
        api.getTasks('completed', 20),
        api.getOverdueTasks(),
        api.getTasksDueSoon(24),
      ]);
      setTasks(pendingData);
      setCompletedTasks(completedData);
      setOverdueTasks(overdueData);
      setDueSoonTasks(dueSoonData);
    } catch (err) {
      console.error('Failed to load tasks:', err);
    } finally {
      setLoading(false);
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!newTask.title.trim() || creating) return;
    
    setCreating(true);
    try {
      const task = await api.createTask(
        newTask.title,
        newTask.description || undefined,
        newTask.priority
      );
      setTasks([task, ...tasks]);
      setNewTask({ title: '', description: '', priority: 'medium' });
      setShowAddForm(false);
    } catch (err) {
      console.error('Failed to create task:', err);
    } finally {
      setCreating(false);
    }
  }

  async function handleComplete(id: string) {
    try {
      const completed = await api.completeTask(id);
      setTasks(tasks.filter((t) => t.id !== id));
      setOverdueTasks(overdueTasks.filter((t) => t.id !== id));
      setDueSoonTasks(dueSoonTasks.filter((t) => t.id !== id));
      setCompletedTasks([completed, ...completedTasks]);
    } catch (err) {
      console.error('Failed to complete task:', err);
    }
  }

  async function handleDelete(id: string, isCompleted = false) {
    if (!confirm('Are you sure you want to delete this task?')) return;
    
    try {
      await api.deleteTask(id);
      if (isCompleted) {
        setCompletedTasks(completedTasks.filter((t) => t.id !== id));
      } else {
        setTasks(tasks.filter((t) => t.id !== id));
        setOverdueTasks(overdueTasks.filter((t) => t.id !== id));
        setDueSoonTasks(dueSoonTasks.filter((t) => t.id !== id));
      }
    } catch (err) {
      console.error('Failed to delete task:', err);
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-400"></div>
      </div>
    );
  }

  return (
    <div className="space-y-4 md:space-y-6">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <h1 className="text-2xl md:text-3xl font-bold text-white">Tasks</h1>
          <p className="text-slate-400 mt-1 text-sm md:text-base">Manage your to-do list.</p>
        </div>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="flex items-center gap-2 bg-blue-600 text-white px-3 py-2 md:px-4 rounded-lg hover:bg-blue-700 active:bg-blue-800 transition-colors flex-shrink-0"
        >
          <Plus className="w-5 h-5" />
          <span className="hidden md:inline">Add Task</span>
        </button>
      </div>

      {showAddForm && (
        <div className="bg-slate-900 rounded-xl p-4 md:p-6 border border-slate-700">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-white">New Task</h2>
            <button
              onClick={() => setShowAddForm(false)}
              className="p-1 text-slate-400 hover:text-white transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
          <form onSubmit={handleCreate} className="space-y-4">
            <input
              type="text"
              value={newTask.title}
              onChange={(e) => setNewTask({ ...newTask, title: e.target.value })}
              placeholder="Task title"
              className="w-full bg-slate-800 text-white rounded-lg px-4 py-3 border border-slate-600 focus:outline-none focus:border-blue-500 text-base"
              autoFocus
            />
            <textarea
              value={newTask.description}
              onChange={(e) => setNewTask({ ...newTask, description: e.target.value })}
              placeholder="Description (optional)"
              className="w-full bg-slate-800 text-white rounded-lg px-4 py-3 border border-slate-600 focus:outline-none focus:border-blue-500 min-h-[80px] text-base"
            />
            <select
              value={newTask.priority}
              onChange={(e) => setNewTask({ ...newTask, priority: e.target.value })}
              className="w-full md:w-auto bg-slate-800 text-white rounded-lg px-4 py-3 border border-slate-600 focus:outline-none focus:border-blue-500 text-base"
            >
              <option value="low">Low Priority</option>
              <option value="medium">Medium Priority</option>
              <option value="high">High Priority</option>
              <option value="urgent">Urgent</option>
            </select>
            <div className="flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setShowAddForm(false)}
                className="px-4 py-2 text-slate-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={creating || !newTask.title.trim()}
                className="bg-blue-600 text-white px-4 py-2 rounded-lg hover:bg-blue-700 disabled:opacity-50 transition-colors"
              >
                {creating ? 'Creating...' : 'Create'}
              </button>
            </div>
          </form>
        </div>
      )}

      {overdueTasks.length > 0 && (
        <div className="bg-red-900/30 rounded-xl border border-red-700">
          <div className="p-3 md:p-4 border-b border-red-700/50">
            <h2 className="text-base font-semibold text-red-300 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4" />
              Overdue ({overdueTasks.length})
            </h2>
          </div>
          <ul className="divide-y divide-red-700/50">
            {overdueTasks.map((task) => (
              <TaskItem
                key={task.id}
                task={task}
                onComplete={() => handleComplete(task.id)}
                onDelete={() => handleDelete(task.id)}
                isOverdue
              />
            ))}
          </ul>
        </div>
      )}

      {dueSoonTasks.length > 0 && (
        <div className="bg-yellow-900/30 rounded-xl border border-yellow-700">
          <div className="p-3 md:p-4 border-b border-yellow-700/50">
            <h2 className="text-base font-semibold text-yellow-300 flex items-center gap-2">
              <Clock className="w-4 h-4" />
              Due Soon ({dueSoonTasks.length})
            </h2>
          </div>
          <ul className="divide-y divide-yellow-700/50">
            {dueSoonTasks.map((task) => (
              <TaskItem
                key={task.id}
                task={task}
                onComplete={() => handleComplete(task.id)}
                onDelete={() => handleDelete(task.id)}
              />
            ))}
          </ul>
        </div>
      )}

      <div className="bg-slate-900 rounded-xl border border-slate-700">
        <div className="p-3 md:p-4 border-b border-slate-700">
          <h2 className="text-base font-semibold text-white flex items-center gap-2">
            <Clock className="w-4 h-4 text-blue-400" />
            Pending ({tasks.length})
          </h2>
        </div>
        
        {tasks.length === 0 ? (
          <div className="p-8 md:p-12 text-center">
            <CheckSquare className="w-10 h-10 md:w-12 md:h-12 text-slate-600 mx-auto mb-4" />
            <p className="text-slate-400">No pending tasks.</p>
            <p className="text-slate-500 text-sm mt-2">Add a task to get started.</p>
          </div>
        ) : (
          <ul className="divide-y divide-slate-700">
            {tasks.map((task) => (
              <TaskItem
                key={task.id}
                task={task}
                onComplete={() => handleComplete(task.id)}
                onDelete={() => handleDelete(task.id)}
              />
            ))}
          </ul>
        )}
      </div>

      <div className="bg-slate-900 rounded-xl border border-slate-700">
        <button
          onClick={() => setShowCompleted(!showCompleted)}
          className="w-full p-3 md:p-4 flex items-center justify-between text-left active:bg-slate-800 transition-colors"
        >
          <h2 className="text-base font-semibold text-slate-400 flex items-center gap-2">
            <Check className="w-4 h-4 text-green-400" />
            Completed ({completedTasks.length})
          </h2>
          <span className="text-slate-500 text-sm">{showCompleted ? 'Hide' : 'Show'}</span>
        </button>
        
        {showCompleted && completedTasks.length > 0 && (
          <ul className="divide-y divide-slate-700 border-t border-slate-700">
            {completedTasks.map((task) => (
              <TaskItem
                key={task.id}
                task={task}
                completed
                onDelete={() => handleDelete(task.id, true)}
              />
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function TaskItem({
  task,
  completed = false,
  isOverdue = false,
  onComplete,
  onDelete,
}: {
  task: Task;
  completed?: boolean;
  isOverdue?: boolean;
  onComplete?: () => void;
  onDelete: () => void;
}) {
  const priorityColors: Record<string, string> = {
    low: 'bg-slate-600 text-slate-200',
    medium: 'bg-blue-600 text-blue-100',
    high: 'bg-orange-600 text-orange-100',
    urgent: 'bg-red-600 text-red-100',
  };

  const taskIsOverdue = isOverdue || (task.due_at && new Date(task.due_at) < new Date() && !completed);

  return (
    <li className="p-3 md:p-4 flex items-start gap-3">
      {!completed && onComplete && (
        <button
          onClick={onComplete}
          className="mt-0.5 w-6 h-6 rounded-full border-2 border-slate-500 hover:border-green-400 active:bg-green-400/30 transition-colors flex-shrink-0 flex items-center justify-center"
        >
          <span className="sr-only">Complete</span>
        </button>
      )}
      {completed && (
        <div className="mt-0.5 w-6 h-6 rounded-full bg-green-600 flex items-center justify-center flex-shrink-0">
          <Check className="w-4 h-4 text-white" />
        </div>
      )}
      
      <div className="flex-1 min-w-0">
        <p className={`font-medium text-sm md:text-base ${completed ? 'text-slate-500 line-through' : 'text-slate-200'}`}>
          {task.title}
        </p>
        {task.description && (
          <p className="text-slate-500 text-sm mt-1 line-clamp-2">{task.description}</p>
        )}
        <div className="flex flex-wrap items-center gap-2 mt-2">
          <span className={`text-xs px-2 py-0.5 rounded ${priorityColors[task.priority]}`}>
            {task.priority}
          </span>
          {task.due_at && (
            <span className={`text-xs flex items-center gap-1 ${taskIsOverdue ? 'text-red-400' : 'text-slate-500'}`}>
              {taskIsOverdue && <AlertTriangle className="w-3 h-3" />}
              {new Date(task.due_at).toLocaleDateString()}
            </span>
          )}
        </div>
      </div>
      
      <button
        onClick={onDelete}
        className="text-slate-500 hover:text-red-400 active:text-red-500 transition-colors p-1 flex-shrink-0"
      >
        <Trash2 className="w-5 h-5" />
      </button>
    </li>
  );
}
