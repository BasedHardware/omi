import { PluginsResult } from '@/src/types/memory.types';
import Markdown from 'markdown-to-jsx';
import { Suspense } from 'react';
import IndentifyPlugin from '../../plugins/indentify-plugin';

interface PuglinsProps {
  puglins: PluginsResult[];
}

export default function Puglins({ puglins }: PuglinsProps) {
  return (
    <div className="mt-10">
      <h3 className="text-xl font-semibold md:text-2xl">Puglins</h3>
      {puglins.map((puglin, index) => {
        return (
          <div key={index} className="mt-3">
            <Suspense>
              <IndentifyPlugin pluginId={puglin.plugin_id} />
            </Suspense>
            <Markdown className="prose text-white prose-ul:list-disc prose-p:m-0 prose-p:mt-3 prose-ul:my-0 prose-slate prose-p:text-white prose-li:text-zinc-400 prose-strong:text-white last:prose-p:text-zinc-300 last:prose-p:bg-zinc-900 last:prose-p:p-2 last:prose-p:px-4 last:prose-p:rounded-lg">
              {puglin.content}
            </Markdown>
          </div>
        );
      })}
    </div>
  );
}
