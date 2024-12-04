import AppList from './components/app-list';
import { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Omi Apps - Discover and Install Apps',
  description: 'Browse and install apps for your Omi device.',
};

export default async function AppsPage() {
  return (
    <main className="min-h-screen bg-[#0B0F17]">
      <AppList />
    </main>
  );
}
