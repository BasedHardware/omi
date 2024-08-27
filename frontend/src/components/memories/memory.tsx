import { Memory as MemoryType } from "@/src/types/memory.types";
import moment from "moment";
import Summary from "./sumary";
import Tabs from "./tabs";

export default function Memory({ memory }: { memory: MemoryType }){
  return (
    <div className="text-white max-w-screen-md mx-auto mt-12 border border-solid border-zinc-800 py-12 rounded-2xl">
      <div className="px-12">
        <h2 className="text-3xl font-bold">
          {memory.structured.title}
        </h2>
        <p className="text-gray-500 my-2">
          {moment(memory.created_at).format("MMMM Do YYYY, h:mm:ss a")}
        </p>
        <span className="bg-gray-700 py-1 px-3 rounded-full text-sm">
          {memory.structured.emoji} {memory.structured.category}
        </span>
      </div>
      <Tabs currentTab="sum" />
      <div className="px-12">
        <Summary memory={memory} />
      </div>
    </div>
  )
}