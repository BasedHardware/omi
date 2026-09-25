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
                <Markdown className="sn-md">{app.content}</Markdown>
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
