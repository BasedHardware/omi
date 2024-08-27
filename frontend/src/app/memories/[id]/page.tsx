export default function MemoryPage({ params }) {
  const memoryId = params.id;

  return (
    <main className="">
      Memory page {memoryId}
    </main>
  );
}
