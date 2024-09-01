import { PluginsResult } from "@/src/types/memory.types";
import Markdown from 'markdown-to-jsx'
import { Suspense } from "react";
import IndentifyPlugin from "../../plugins/indentify-plugin";

interface PuglinsProps{
  puglins: PluginsResult[];
}

export default function Puglins({ puglins }: PuglinsProps) {
  return (
    <div className="mt-10">
      <h3 className="text-xl font-semibold md:text-2xl">Puglins</h3>
      {puglins.map((puglin, index) => {
        return(
          <div key={index} className="mt-3">
            <Suspense>
              <IndentifyPlugin pluginId={puglin.plugin_id} />
            </Suspense>
            <Markdown className="prose prose-ul:list-disc text-white">{puglin.content}</Markdown>
          </div>
        )
      })}
    </div>
  )
}