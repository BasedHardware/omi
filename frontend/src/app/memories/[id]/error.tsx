'use client';

export default function Error() {
  console.log('Memory not found');
  return (
    <div className="mx-auto my-28 max-w-screen-md rounded-2xl border border-solid border-zinc-800 px-12 py-12 text-white">
      <h1 className="font-semibolds text-xl">Memory not found</h1>
      <p className="mt-3 text-lg text-zinc-400">
        The memory you are looking for does not exist. Please check the URL and try again.
      </p>
    </div>
  );
}
