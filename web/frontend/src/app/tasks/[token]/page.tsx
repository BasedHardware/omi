import getSharedTasks from '@/src/actions/tasks/get-shared-tasks';
import envConfig from '@/src/constants/envConfig';
import { ParamsTypes } from '@/src/types/params.types';
import { Metadata, ResolvingMetadata } from 'next';
import { notFound } from 'next/navigation';
import moment from 'moment';

interface SharedTasksPageProps {
  params: { token: string };
}

export async function generateMetadata(
  { params }: SharedTasksPageProps,
  parent: ResolvingMetadata,
): Promise<Metadata> {
  const prevData = (await parent) as Metadata;
  const data = await getSharedTasks(params.token);

  const title = !data
    ? 'Tasks Not Found'
    : `${data.sender_name} shared ${data.count} task${data.count !== 1 ? 's' : ''} with you`;

  const description = data
    ? data.tasks.map((t) => t.description).join(' | ')
    : 'These shared tasks are no longer available.';

  return {
    title,
    metadataBase: prevData.metadataBase,
    description,
    robots: { follow: true, index: false },
    openGraph: {
      ...prevData.openGraph,
      title,
      type: 'website',
      url: `${prevData.metadataBase}/tasks/${params.token}`,
      description,
    },
  };
}

export default async function SharedTasksPage({ params }: SharedTasksPageProps) {
  const data = await getSharedTasks(params.token);
  if (!data) {
    notFound();
  }

  return (
    <div className="min-h-screen bg-gradient-to-b from-[#1a0a1f] via-[#0a0a2f] to-black font-system-ui">
      <div className="absolute inset-0 bg-[radial-gradient(circle_500px_at_50%_200px,rgba(88,28,135,0.2),transparent)]" />
      <section className="relative mx-auto max-w-screen-md px-6 py-16 md:px-12 md:py-24">
        <div className="relative z-10 text-white">
          <div className="flex flex-col gap-3 pt-6 md:pt-8">
            <h2 className="text-2xl font-medium tracking-wide md:text-3xl">
              {data.sender_name} shared {data.count} task{data.count !== 1 ? 's' : ''} with you
            </h2>
            <p className="text-sm text-zinc-400">
              Open in the Omi app to add these tasks to your list.
            </p>
          </div>

          <div className="mt-8 flex flex-col gap-3">
            {data.tasks.map((task, index) => (
              <div
                key={index}
                className="flex items-start gap-3 rounded-lg border border-zinc-800 bg-zinc-900/50 p-4"
              >
                <div className="mt-0.5 flex h-5 w-5 flex-shrink-0 items-center justify-center rounded-full border border-zinc-600">
                  <span className="text-xs text-zinc-500">{index + 1}</span>
                </div>
                <div className="flex-1">
                  <p className="text-base leading-relaxed text-zinc-200">{task.description}</p>
                  {task.due_at && (
                    <p className="mt-1.5 text-xs text-zinc-500">
                      Due {moment(task.due_at).format('MMM D, YYYY')}
                    </p>
                  )}
                </div>
              </div>
            ))}
          </div>

          <div className="mt-10 flex justify-center">
            <a
              href="https://apps.apple.com/app/omi-ai/id6502156163"
              className="inline-flex items-center gap-2 rounded-full bg-white px-6 py-3 text-sm font-medium text-black transition hover:bg-zinc-200"
            >
              Get Omi App
            </a>
          </div>
        </div>
      </section>
    </div>
  );
}
