export default function Loading() {
  return (
    <div className="min-h-screen bg-black text-white flex items-center justify-center">
      <div className="animate-pulse">
        <div className="h-8 w-32 bg-gray-700 rounded mb-4" />
        <div className="h-4 w-48 bg-gray-700 rounded" />
      </div>
    </div>
  )
}