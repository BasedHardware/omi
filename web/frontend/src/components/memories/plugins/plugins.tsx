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
              <div className="mb-6 md:mb-8">
                <Markdown className="font-system-ui prose prose-base max-w-none text-zinc-300 md:prose-lg prose-headings:text-base prose-headings:font-medium prose-headings:text-zinc-100 prose-h1:text-base prose-h2:text-base prose-h3:text-base prose-h4:text-base prose-h5:text-base prose-h6:text-base prose-p:leading-relaxed prose-p:text-zinc-300 prose-strong:text-zinc-100 prose-ul:text-zinc-300 prose-li:text-zinc-300 prose-li:marker:text-zinc-500 md:prose-h1:text-base md:prose-h2:text-base md:prose-h3:text-base md:prose-h4:text-base md:prose-h5:text-base md:prose-h6:text-base">
                  {app.content}
                </Markdown>
              </div>
              <ErrorBoundary errorComponent={ErrorIdentifyPlugin}>
                <IdentifyPlugin pluginId={app.app_id} />
              </ErrorBoundary>
            </div>
          );
        })}
      </div>
    </div>
  );
}
