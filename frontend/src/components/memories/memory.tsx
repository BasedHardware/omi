import { Memory as MemoryType } from "@/src/types/memory.types";

export default function Memory({ memory }: { memory: MemoryType }){
  return (
    <div className="text-white">
      {JSON.stringify(memory)}
    </div>
  )
}