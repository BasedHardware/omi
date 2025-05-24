import { Suspense } from 'react';
import { LoadingFallback } from './_components/loading-fallback';
import { ChatContent } from './content';

export default function ChatPage() {
  return (
    <Suspense fallback={<LoadingFallback />}>
      <ChatContent />
    </Suspense>
  );
}