import { Memory } from '@/src/types/memory.types';
import ActionItems from './action-items';
import MemoryEvents from '../events/memory-events';
import Plugins from '../plugins/plugins';
import Markdown from 'markdown-to-jsx';

interface SummaryProps {
  memory: Memory;
}

export default function Summary({ memory }: SummaryProps) {
  const overview = (memory?.structured?.overview || '').trim();

  return (
    <div className="flex flex-col gap-12">
      {overview && (
        <div className="mt-8 md:mt-10">
          <Markdown
            className="font-system-ui prose prose-base max-w-none text-zinc-200 md:prose-lg prose-headings:mb-3 prose-headings:mt-8 prose-headings:text-lg prose-headings:font-semibold prose-headings:text-white first:prose-headings:mt-0 prose-h1:text-xl prose-h2:text-lg prose-h3:text-base prose-p:leading-7 prose-p:text-zinc-200 prose-a:text-zinc-100 prose-a:underline prose-strong:text-white prose-ol:my-3 prose-ol:text-zinc-200 prose-ul:my-3 prose-ul:text-zinc-200 prose-li:my-1 prose-li:text-zinc-200 prose-li:marker:text-zinc-500 md:prose-h1:text-2xl md:prose-h2:text-xl md:prose-h3:text-lg"
            options={{ forceBlock: true }}
          >
            {overview}
          </Markdown>
        </div>
      )}

      {memory.apps_results.length > 0 && (
        <div className={overview ? '' : 'mt-8 md:mt-10'}>
          <Plugins apps={memory.apps_results} />
        </div>
      )}

      {memory?.structured?.events?.length > 0 && (
        <div>
          <MemoryEvents events={memory.structured.events} />
        </div>
      )}

      {memory?.structured?.action_items?.length > 0 && (
        <div>
          <ActionItems items={memory.structured.action_items} />
        </div>
      )}
    </div>
  );
}
