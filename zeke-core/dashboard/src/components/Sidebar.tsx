import { NavLink } from 'react-router-dom';
import { LayoutDashboard, MessageSquare, Brain, CheckSquare, Sparkles, X, Zap } from 'lucide-react';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Dashboard', gradient: 'from-blue-500 to-cyan-500' },
  { to: '/chat', icon: MessageSquare, label: 'Chat', gradient: 'from-green-500 to-emerald-500' },
  { to: '/memories', icon: Brain, label: 'Memories', gradient: 'from-cyan-500 to-blue-600' },
  { to: '/tasks', icon: CheckSquare, label: 'Tasks', gradient: 'from-amber-500 to-orange-500' },
  { to: '/curation', icon: Sparkles, label: 'Curation', gradient: 'from-purple-500 to-pink-600' },
];

interface SidebarProps {
  onClose?: () => void;
}

export function Sidebar({ onClose }: SidebarProps) {
  return (
    <aside className="w-64 bg-gradient-to-b from-slate-900 to-slate-950 min-h-screen flex flex-col border-r border-slate-700/50 md:fixed md:inset-y-0 md:left-0">
      <div className="p-6 border-b border-slate-700/50 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-xl shadow-lg shadow-blue-500/25">
            <Zap className="w-5 h-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent">ZEKE</h1>
            <p className="text-xs text-slate-500 mt-0.5">Personal AI Assistant</p>
          </div>
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="p-2 -mr-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-all md:hidden"
            aria-label="Close menu"
          >
            <X className="w-5 h-5" />
          </button>
        )}
      </div>
      
      <nav className="flex-1 p-4">
        <ul className="space-y-1.5">
          {navItems.map((item) => (
            <li key={item.to}>
              <NavLink
                to={item.to}
                onClick={onClose}
                className={({ isActive }) =>
                  `flex items-center gap-3 px-4 py-3 rounded-xl transition-all ${
                    isActive
                      ? `bg-gradient-to-r ${item.gradient} text-white shadow-lg`
                      : 'text-slate-400 hover:bg-slate-800/50 hover:text-white'
                  }`
                }
              >
                <item.icon className="w-5 h-5" />
                <span className="font-medium">{item.label}</span>
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>
      
      <div className="p-4 border-t border-slate-700/50">
        <div className="px-4 py-3 bg-gradient-to-br from-slate-800/80 to-slate-900/80 rounded-xl border border-slate-700/50">
          <div className="flex items-center justify-between">
            <p className="text-xs text-slate-500 uppercase tracking-wide">Status</p>
            <span className="w-2 h-2 bg-green-400 rounded-full animate-pulse"></span>
          </div>
          <p className="text-sm text-green-400 font-medium mt-1">
            Online
          </p>
        </div>
      </div>
    </aside>
  );
}
