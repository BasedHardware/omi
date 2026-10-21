import getSharedMemory from '@/src/actions/memories/get-shared-memory';
import { shareLinkHeader, sharedConversationMarkdown } from '@/src/lib/shared-export.mjs';

export const dynamic = 'force-dynamic';

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const { id } = await params;
  const format = new URL(request.url).searchParams.get('format');
  const headers = {
    Vary: 'Accept',
    Link: shareLinkHeader(id),
    'Cache-Control': 'private, no-store',
  };
  const memory = await getSharedMemory(id);
  if (!memory)
    return Response.json(
      { error: 'Shared conversation not found' },
      { status: 404, headers },
    );
  if (format === 'md') {
    return new Response(sharedConversationMarkdown(memory, id), {
      headers: { ...headers, 'Content-Type': 'text/markdown; charset=utf-8' },
    });
  }
  return Response.json(memory, { headers });
}
