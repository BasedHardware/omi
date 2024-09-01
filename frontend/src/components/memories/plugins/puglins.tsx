import { PluginsResult } from '@/src/types/memory.types';
import Markdown from 'markdown-to-jsx';
import { Suspense } from 'react';
import IndentifyPlugin from '../../plugins/indentify-plugin';
import IdentifyPluginLoader from '../../plugins/identify-plugin-loader';

interface PuglinsProps {
  puglins: PluginsResult[];
}

export default function Puglins({ puglins }: PuglinsProps) {
  return (
    <div className='h-auto'>
      <h3 className="text-xl font-semibold px-4 md:px-12 md:text-2xl">Puglins</h3>
      <div className='flex gap-8 flex-col mt-3'>
        {puglins.map((puglin, index) => {
          return (
            <div key={index}>
              <Suspense fallback={<IdentifyPluginLoader />}>
                <IndentifyPlugin pluginId={puglin.plugin_id} />
              </Suspense>
              <div className='px-4 md:px-12 bg-[#0f0f0f]'>
                <Markdown className="prose text-white prose-ul:list-disc prose-p:m-0 prose-p:mt-3 prose-ul:my-0 prose-slate prose-p:text-white prose-li:text-zinc-400 prose-strong:text-white last:prose-p:text-zinc-300 last:prose-p:bg-zinc-900 last:prose-p:p-2 last:prose-p:px-4 last:prose-p:rounded-lg last:prose-p:text-sm last:prose-p:mt-8">
                  {puglin.content}
                </Markdown>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
