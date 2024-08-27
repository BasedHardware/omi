'use client';

export default function Error() {
  console.log('Memory not found');
  return (
    <div className="mx-auto my-28 max-w-screen-md rounded-2xl border border-solid border-zinc-800 py-12 text-white px-12">
      <h1 className="text-xl font-semibolds">Memory not found</h1>
      <p className="text-lg text-zinc-400 mt-3">
        The memory you are looking for does not exist. Please check the URL and try again.
      </p>
    </div>
  );
}
