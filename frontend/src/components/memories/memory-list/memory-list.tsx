import getPublicMemories from "@/src/actions/memories/get-public-memories";
import Link from "next/link";

export default async function MemoryList(){
  const memories = await getPublicMemories();
  return(
    <div className="text-white max-w-screen-md mx-auto md:my-28 my-10">
      <div className="flex flex-col gap-5">
        {memories.map((memory) => (
          <Link key={memory.id} className="mb-4" href={`memories/${memory.id}`}>
            <div className="text-2xl font-bold">{!memory?.structured?.title ? 'Untitle memory': memory.structured.title}</div>
            <div className="line-clamp-3 text-base font-extralight">{!memory?.structured?.overview ? "This memory doesn't have an overview" : memory?.structured?.overview}</div>
          </Link>
        ))}
      </div>
    </div>
  )
}