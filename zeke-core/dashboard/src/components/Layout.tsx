import { useState } from 'react';
import { Outlet } from 'react-router-dom';
import { BottomNav } from './BottomNav';
import { Sidebar } from './Sidebar';
import { MobileHeader } from './MobileHeader';

export function Layout() {
  const [sidebarOpen, setSidebarOpen] = useState(false);

  return (
    <div className="min-h-screen bg-slate-950">
      <MobileHeader onMenuClick={() => setSidebarOpen(true)} />
      
      <div className="hidden md:block">
        <Sidebar />
      </div>
      
      {sidebarOpen && (
        <>
          <div 
            className="fixed inset-0 bg-black/50 z-40 md:hidden"
            onClick={() => setSidebarOpen(false)}
          />
          <div className="fixed inset-y-0 left-0 z-50 md:hidden">
            <Sidebar onClose={() => setSidebarOpen(false)} />
          </div>
        </>
      )}
      
      <main className="pb-20 pt-16 px-4 md:pb-8 md:pt-8 md:px-8 md:ml-64 min-h-screen">
        <Outlet />
      </main>
      
      <BottomNav />
    </div>
  );
}
