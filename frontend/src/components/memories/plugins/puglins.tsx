import { PluginsResult } from "@/src/types/memory.types";

interface PuglinsProps{
  puglins: PluginsResult[];
}
export default function Puglins({ puglins }: PuglinsProps) {
  return (
    <div className="mt-10">
      <h3 className="text-xl font-semibold md:text-2xl">Puglins</h3>
      {puglins.map((puglin, index) => (
        <div key={index} className="mt-3">
          <h4 className="text-lg font-semibold">{puglin.plugin_id}</h4>
          <p className="mt-2 text-base">{puglin.content}</p>
        </div>
      ))}
    </div>
  )
}