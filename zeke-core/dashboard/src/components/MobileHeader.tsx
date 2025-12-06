import { Menu } from 'lucide-react';

interface MobileHeaderProps {
  onMenuClick: () => void;
}

export function MobileHeader({ onMenuClick }: MobileHeaderProps) {
  return (
    <header className="fixed top-0 left-0 right-0 h-14 bg-slate-900 border-b border-slate-700 flex items-center justify-between px-4 z-30 md:hidden safe-area-top">
      <button
        onClick={onMenuClick}
        className="p-2 -ml-2 text-slate-400 active:text-white transition-colors"
        aria-label="Open menu"
      >
        <Menu className="w-6 h-6" />
      </button>
      
      <h1 className="text-lg font-bold text-blue-400">ZEKE</h1>
      
      <div className="w-10" />
    </header>
  );
}
