export default function MemoryPage({ params }) {
  const memoryId = params.id;

  return (
    <main className="flex min-h-screen flex-col items-center justify-between p-24">
      Memory page {memoryId}
    </main>
  );
}
