export default function MyAppsLoading() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-[#0B0F17] text-white">
      <div className="text-center">
        <div className="mb-4 h-8 w-8 animate-spin rounded-full border-4 border-gray-300 border-t-white"></div>
        <p>Loading your apps...</p>
      </div>
    </div>
  );
}