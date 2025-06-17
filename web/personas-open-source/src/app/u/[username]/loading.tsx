export default function Loading() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-black text-white">
      <div className="animate-pulse">
        <div className="mb-4 h-8 w-32 rounded bg-gray-700" />
        <div className="h-4 w-48 rounded bg-gray-700" />
      </div>
    </div>
  );
}
