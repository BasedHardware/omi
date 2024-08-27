import { Memory as MemoryType } from "@/src/types/memory.types";
import moment from "moment";
import ActionItems from "./action-items";

export default function Memory({ memory }: { memory: MemoryType }){
  return (
    <div className="text-white">
      <h2>
        {memory.structured.title}
      </h2>
      <p>
        {moment(memory.created_at).format("MMMM Do YYYY, h:mm:ss a")}
      </p>
      <span>
        {memory.structured.emoji} {memory.structured.category}
      </span>
      <div>
        <h3>
          Overview
        </h3>
        <p>
          {memory.structured.overview}
        </p>
      </div>
      <ActionItems items={memory.structured.action_items} />
    </div>
  )
}