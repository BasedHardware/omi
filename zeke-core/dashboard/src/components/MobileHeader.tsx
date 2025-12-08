import { Menu, Zap } from 'lucide-react';

interface MobileHeaderProps {
  onMenuClick: () => void;
}

export function MobileHeader({ onMenuClick }: MobileHeaderProps) {
  return (
    <header className="fixed top-0 left-0 right-0 h-14 bg-slate-900/95 backdrop-blur-lg border-b border-slate-700/50 flex items-center justify-between px-4 z-30 md:hidden safe-area-top">
      <button
        onClick={onMenuClick}
        className="p-2 -ml-2 text-slate-400 hover:text-white hover:bg-slate-800 rounded-lg transition-all"
        aria-label="Open menu"
      >
        <Menu className="w-5 h-5" />
      </button>
      
      <div className="flex items-center gap-2">
        <div className="p-1.5 bg-gradient-to-br from-blue-500 to-cyan-500 rounded-lg shadow-lg shadow-blue-500/25">
          <Zap className="w-4 h-4 text-white" />
        </div>
        <h1 className="text-lg font-bold bg-gradient-to-r from-blue-400 to-cyan-400 bg-clip-text text-transparent">ZEKE</h1>
      </div>
      
      <div className="w-10" />
    </header>
  );
}
