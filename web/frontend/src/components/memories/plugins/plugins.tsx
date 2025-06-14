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
      <h3 className="px-4 text-xl font-semibold md:px-12 md:text-2xl">App Summary</h3>
      <div className="mt-3 flex flex-col gap-8">
        {apps.map((app, index) => {
          return (
            <div key={index}>
              <ErrorBoundary errorComponent={ErrorIdentifyPlugin}>
                <IdentifyPlugin pluginId={app.app_id} />
              </ErrorBoundary>
              <div className="bg-bg-color px-4 md:px-12">
                <Markdown className="prose md:prose-p:text-lg text-white prose-headings:text-gray-200 prose-strong:text-white prose-ul:text-gray-300 prose-li:text-gray-300 prose-p:m-0 prose-p:mt-3 last:prose-p:mt-8 last:prose-p:rounded-lg last:prose-p:bg-zinc-900 last:prose-p:p-2 last:prose-p:px-4 last:prose-p:text-zinc-200 md:last:prose-p:text-sm">
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
