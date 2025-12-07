import { NavLink } from 'react-router-dom';
import { LayoutDashboard, MessageSquare, Brain, CheckSquare, Sparkles } from 'lucide-react';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Home' },
  { to: '/chat', icon: MessageSquare, label: 'Chat' },
  { to: '/memories', icon: Brain, label: 'Memory' },
  { to: '/tasks', icon: CheckSquare, label: 'Tasks' },
  { to: '/curation', icon: Sparkles, label: 'Curate' },
];

export function BottomNav() {
  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-slate-900 border-t border-slate-700 z-30 md:hidden safe-area-bottom">
      <ul className="flex justify-around items-center h-16">
        {navItems.map((item) => (
          <li key={item.to} className="flex-1">
            <NavLink
              to={item.to}
              className={({ isActive }) =>
                `flex flex-col items-center justify-center py-2 min-h-[56px] transition-colors ${
                  isActive
                    ? 'text-blue-400'
                    : 'text-slate-400 active:text-slate-200'
                }`
              }
            >
              <item.icon className="w-6 h-6" />
              <span className="text-xs mt-1 font-medium">{item.label}</span>
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
