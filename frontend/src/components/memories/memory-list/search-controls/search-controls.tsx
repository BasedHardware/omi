import SearchBar from './search-bar';

export default function SearchControls() {
  return (
    <div>
      <h1 className="text-center text-3xl font-bold text-white">Memories</h1>
      <div className="mb-5 mt-8 flex w-full items-center gap-2">
        <SearchBar />
        {/* <CategoriesDropdown /> */}
      </div>
    </div>
  );
}
