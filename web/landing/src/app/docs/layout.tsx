import { Navbar } from '@/components/navbar';
import { DocsSidebar } from '@/components/docs-sidebar';
import { brand } from '@/lib/config';

export const metadata = {
  title: `Documentation — ${brand.name}`,
  description: `${brand.name} developer documentation, guides, and API reference.`,
};

export default function DocsLayout({ children }: { children: React.ReactNode }) {
  return (
    <>
      <Navbar />
      <div className="min-h-screen pt-16">
        <DocsSidebar />
        <main className="lg:ml-64 border-l border-white/5 min-h-[calc(100vh-4rem)] px-8 md:px-16 lg:px-20 py-16">
          <div className="max-w-3xl">{children}</div>
        </main>
      </div>
    </>
  );
}
