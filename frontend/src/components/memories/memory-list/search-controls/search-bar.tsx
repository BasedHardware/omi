export default function SearchBar() {
  return (
    <div className="mb-10 mt-5">
      <input
        type="text"
        placeholder="Search memories"
        className="w-full rounded-md border border-solid border-zinc-600 bg-transparent px-3 py-2"
      />
    </div>
  );
}
