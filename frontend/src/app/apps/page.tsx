// import { useState, useEffect } from 'react';
import envConfig from '@/src/constants/envConfig';
import { Button } from '@/src/components/ui/button';
import { Star, DollarSign, Download, Moon, Sun } from 'lucide-react';
import Link from 'next/link';
// import { Button } from '@/components/ui/button';

interface ExternalIntegration {
  // Define ExternalIntegration properties here if needed
}

interface PluginReview {
  // Define PluginReview properties here if needed
}

export interface Plugin {
  id: string;
  name: string;
  author: string;
  description: string;
  image: string; // TODO: return image_url: string with the whole repo + path
  capabilities: Set<string>;
  memory_prompt?: string;
  chat_prompt?: string;
  external_integration?: ExternalIntegration;
  reviews: PluginReview[];
  user_review?: PluginReview;
  rating_avg: number;
  rating_count: number;
  installs: number;
  enabled: boolean;
  deleted: boolean;
  trigger_workflow_memories: boolean;
}

export interface PluginStat {
  id: string;
  money: number,
}


// const plugins: Plugin[] = [
//   {
//     id: '1',
//     name: 'Super Formatter',
//     author: 'Jane Doe',
//     description: 'A powerful code formatter that supports multiple languages.',
//     image: 'https://via.placeholder.com/100',
//     capabilities: new Set(['formatting', 'multi-language']),
//     reviews: [],
//     rating_avg: 4.5,
//     rating_count: 120,
//     downloads: 5000,
//     enabled: false,
//     deleted: false,
//     trigger_workflow_memories: true,
//   },
//   {
//     id: '2',
//     name: 'Quick Debugger',
//     author: 'John Smith',
//     description: 'Efficiently debug your code with this smart tool.',
//     image: 'https://via.placeholder.com/100',
//     capabilities: new Set(['debugging']),
//     reviews: [],
//     rating_avg: 4.2,
//     rating_count: 80,
//     downloads: 3000,
//     enabled: false,
//     deleted: false,
//     trigger_workflow_memories: true,
//   },
//   {
//     id: '3',
//     name: 'AI Assistant',
//     author: 'Alex Johnson',
//     description: 'Get AI-powered coding suggestions as you type.',
//     image: 'https://via.placeholder.com/100',
//     capabilities: new Set(['ai', 'code-suggestion']),
//     reviews: [],
//     rating_avg: 4.8,
//     rating_count: 200,
//     downloads: 10000,
//     enabled: false,
//     deleted: false,
//     trigger_workflow_memories: true,
//   },
// ];

export default async function SleekPluginList() {
  // const [darkMode, setDarkMode] = useState(false);

  // useEffect(() => {
  //   if (darkMode) {
  //     document.documentElement.classList.add('dark');
  //   } else {
  //     document.documentElement.classList.remove('dark');
  //   }
  // }, [darkMode]);
  var response = await fetch(`${envConfig.API_URL}/v1/approved-apps?include_reviews=true`);


  const plugins = (await response.json()) as Plugin[];

  response = await fetch("https://raw.githubusercontent.com/BasedHardware/omi/refs/heads/main/community-plugin-stats.json");
  const stats = (await response.json()) as PluginStat[];

  // Sort plugins by downloads in descending order
  const sortedPlugins = plugins.sort((a, b) => b.installs - a.installs);

  return (
    <div className="container mx-auto p-4">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="pt-6 text-3xl font-bold text-gray-800 dark:text-white">Omi Apps Marketplace</h1>
        {/* <button
          variant="outline"
          size="icon"
          onClick={() => setDarkMode(!darkMode)}
          className="rounded-full"
        >
          {darkMode ? (
            <Sun className="h-[1.2rem] w-[1.2rem]" />
          ) : (
            <Moon className="h-[1.2rem] w-[1.2rem]" />
          )}
          <span className="sr-only">Toggle theme</span>
        </button> */}
      </div>
      <div className="grid gap-6 md:grid-cols-2 lg:grid-cols-3">
        {sortedPlugins.map((plugin) => (
          <PluginCard key={plugin.id} plugin={plugin} stat={stats.find((s) => s.id == plugin.id)} />
        ))}
      </div>
      
    </div>
  );
}

function PluginCard({ plugin, stat }: { plugin: Plugin, stat?: PluginStat }) {
  return (
    <div
      key={plugin.id}
      className="flex h-full flex-col items-stretch overflow-hidden rounded-lg bg-white shadow-lg transition-transform duration-300 hover:scale-105 dark:bg-gray-800"
    >
      <div className="flex h-full flex-col p-6">
        <div className="mb-4 flex items-center">
          <img
            src={plugin.image}
            alt={plugin.name}
            className="mr-4 h-16 w-16 rounded-full object-cover"
          />
          <div>
            <h2 className="text-xl font-semibold text-gray-800 dark:text-white">
              {plugin.name}
            </h2>
            <p className="text-sm text-gray-600 dark:text-gray-400">by {plugin.author}</p>
          </div>
        </div>
        <p className="mb-4 text-gray-700 dark:text-gray-300">{plugin.description}</p>
        <div className="flex-1"></div>
        <div className="mb-4 mt-auto flex items-center justify-between">
          <div className="flex items-center">
            <Star className="mr-1 h-5 w-5 text-yellow-400" />
            <span className="mr-2 font-semibold text-gray-800 dark:text-white">
              {plugin.rating_avg?.toFixed(1) ?? 'N/A'}
            </span>
            <span className="text-sm text-gray-600 dark:text-gray-400">
              ({plugin.rating_count ?? 0})
            </span>
          </div>
          <div className="flex items-center">
            <DollarSign className="mb-1 h-5 w-5 text-green-500" />
            <span className="text-sm text-gray-600 dark:text-gray-400">
              {(stat?.money ?? 0).toLocaleString()}
            </span>
          </div>
          <div className="flex items-center">
            <Download className="mr-1 h-5 w-5 text-gray-600 dark:text-gray-400" />
            <span className="text-sm text-gray-600 dark:text-gray-400">
              {plugin.installs.toLocaleString()}
            </span>
          </div>
        </div>
        <Button className="w-full bg-black text-white hover:bg-gray-800" asChild>
          <Link href={`/apps/${plugin.id}`}>View Info</Link>
        </Button>
      </div>
    </div>
  );
}
