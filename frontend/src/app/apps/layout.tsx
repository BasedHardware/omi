export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-100 transition-colors duration-300 dark:bg-gray-900">
      <div className="h-20 w-screen bg-black"></div>
      {children}
    </div>
  );
}
