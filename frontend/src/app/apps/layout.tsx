export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-100 transition-colors duration-300 dark:bg-gray-900">
      {children}
    </div>
  );
}
