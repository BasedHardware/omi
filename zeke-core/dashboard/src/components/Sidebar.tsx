import { NavLink } from 'react-router-dom';
import { LayoutDashboard, MessageSquare, Brain, CheckSquare } from 'lucide-react';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/chat', icon: MessageSquare, label: 'Chat' },
  { to: '/memories', icon: Brain, label: 'Memories' },
  { to: '/tasks', icon: CheckSquare, label: 'Tasks' },
];

export function Sidebar() {
  return (
    <aside className="w-64 bg-slate-900 min-h-screen flex flex-col border-r border-slate-700">
      <div className="p-6 border-b border-slate-700">
        <h1 className="text-2xl font-bold text-blue-400">ZEKE</h1>
        <p className="text-sm text-slate-400 mt-1">Personal AI Assistant</p>
      </div>
      
      <nav className="flex-1 p-4">
        <ul className="space-y-2">
          {navItems.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                    isActive
                      ? 'bg-blue-600 text-white'
                      : 'text-slate-300 hover:bg-slate-800'
                  }`
                }
              >
                <item.icon className="w-5 h-5" />
                <span>{item.label}</span>
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      
      <div className="p-4 border-t border-slate-700">
        <div className="px-4 py-3 bg-slate-800 rounded-lg">
          <p className="text-sm text-slate-400">Status</p>
          <p className="text-sm text-green-400 flex items-center gap-2 mt-1">
            <span className="w-2 h-2 bg-green-400 rounded-full"></span>
            Online
          </p>
        </div>
      </div>
    </aside>
  );
}
