import { NavLink } from 'react-router-dom';
import { LayoutDashboard, MessageSquare, Brain, CheckSquare } from 'lucide-react';

const navItems = [
  { to: '/', icon: LayoutDashboard, label: 'Home', gradient: 'from-blue-500 to-cyan-500' },
  { to: '/chat', icon: MessageSquare, label: 'Chat', gradient: 'from-green-500 to-emerald-500' },
  { to: '/memories', icon: Brain, label: 'Memory', gradient: 'from-cyan-500 to-blue-600' },
  { to: '/tasks', icon: CheckSquare, label: 'Tasks', gradient: 'from-amber-500 to-orange-500' },
];

export function BottomNav() {
  return (
    <nav className="fixed bottom-0 left-0 right-0 bg-slate-900/95 backdrop-blur-lg border-t border-slate-700/50 z-30 md:hidden safe-area-bottom">
      <ul className="flex justify-around items-center h-16">
        {navItems.map((item) => (
          <li key={item.to} className="flex-1">
            <NavLink
              to={item.to}
              className={({ isActive }) =>
                `flex flex-col items-center justify-center py-2 min-h-[56px] transition-all ${
                  isActive
                    ? 'text-white'
                    : 'text-slate-500 active:text-slate-300'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  <div className={`p-1.5 rounded-xl transition-all ${
                    isActive 
                      ? `bg-gradient-to-r ${item.gradient} shadow-lg` 
                      : ''
                  }`}>
                    <item.icon className={`w-5 h-5 ${isActive ? 'text-white' : ''}`} />
                  </div>
                  <span className={`text-[10px] mt-1 font-medium ${
                    isActive ? 'text-white' : ''
                  }`}>{item.label}</span>
                </>
              )}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
