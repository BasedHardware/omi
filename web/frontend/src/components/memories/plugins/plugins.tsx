import { AppsResult } from '@/src/types/memory.types';
import Markdown from 'markdown-to-jsx';
import { ErrorBoundary } from 'next/dist/client/components/error-boundary';
import ErrorIdentifyPlugin from '../../plugins/error-identify-plugin';
import IdentifyPlugin from '../../plugins/identify-plugin';

interface PluginsProps {
  apps: AppsResult[];
}

export default function Plugins({ apps }: PluginsProps) {
  return (
    <div className="h-auto">
      <div className="flex flex-col gap-10">
        {apps.map((app, index) => {
          return (
            <div key={index}>
              <ErrorBoundary errorComponent={ErrorIdentifyPlugin}>
                <IdentifyPlugin pluginId={app.app_id} />
              </ErrorBoundary>
              <div>
                <Markdown className="prose prose-sm max-w-none text-zinc-300 prose-headings:text-zinc-100 prose-headings:font-semibold prose-p:leading-relaxed prose-p:text-zinc-300 prose-strong:text-zinc-100 prose-ul:text-zinc-300 prose-li:text-zinc-300 prose-li:marker:text-zinc-500 md:prose-base">
                  {app.content}
                </Markdown>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
