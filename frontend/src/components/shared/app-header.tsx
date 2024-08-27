export default function AppHeader(){
  return(
    <header className="flex justify-between items-center p-4 text-white">
      <h1 className="text-xl">Base Hardware</h1>
      <nav>
        <ul className="flex space-x-4">
          <li>
            <a href="/" className="hover:underline">Home</a>
          </li>
          <li>
            <a href="/memories" className="hover:underline">Memories</a>
          </li>
        </ul>
      </nav>
    </header>
  )
}