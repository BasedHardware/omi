import { NavLink } from 'react-router-dom';
import { LayoutDashboard, MessageSquare, Brain, CheckSquare, Sparkles, X } from 'lucide-react';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard' },
  { to: '/chat', icon: MessageSquare, label: 'Chat' },
  { to: '/memories', icon: Brain, label: 'Memories' },
  { to: '/tasks', icon: CheckSquare, label: 'Tasks' },
  { to: '/curation', icon: Sparkles, label: 'Curation' },
];

interface SidebarProps {
  onClose?: () => void;
}

export function Sidebar({ onClose }: SidebarProps) {
  return (
    <aside className="w-64 bg-slate-900 min-h-screen flex flex-col border-r border-slate-700 md:fixed md:inset-y-0 md:left-0">
      <div className="p-6 border-b border-slate-700 flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-blue-400">ZEKE</h1>
          <p className="text-sm text-slate-400 mt-1">Personal AI Assistant</p>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="p-2 -mr-2 text-slate-400 active:text-white transition-colors md:hidden"
            aria-label="Close menu"
          >
            <X className="w-6 h-6" />
          </button>
        )}
      </div>
      
      <nav className="flex-1 p-4">
        <ul className="space-y-2">
          {navItems.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                onClick={onClose}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                    isActive
                      ? 'bg-blue-600 text-white'
                      : 'text-slate-300 hover:bg-slate-800 active:bg-slate-700'
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
