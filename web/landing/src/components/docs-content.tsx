import { brand } from '@/lib/config';

interface DocsContentProps {
  title: string;
  description?: string;
  content?: string;
}

export function DocsContent({ title, description, content }: DocsContentProps) {
  return (
    <article className="max-w-3xl">
      <h1 className="font-display font-bold text-3xl md:text-4xl mb-3">{title}</h1>
      {description && <p className="text-text-tertiary text-lg mb-8">{description}</p>}

      {content ? (
        <div className="prose-nooto">
          {content.split('\n\n').map((block, i) => {
            const trimmed = block.trim();
            if (!trimmed) return null;

            if (trimmed.startsWith('## ')) {
              return (
                <h2 key={i} className="font-display font-bold text-xl mt-10 mb-4">
                  {trimmed.replace('## ', '')}
                </h2>
              );
            }
            if (trimmed.startsWith('### ')) {
              return (
                <h3 key={i} className="font-display font-semibold text-lg mt-8 mb-3">
                  {trimmed.replace('### ', '')}
                </h3>
              );
            }
            if (trimmed.startsWith('- ')) {
              const items = trimmed.split('\n').filter((l) => l.startsWith('- '));
              return (
                <ul key={i} className="space-y-2 mb-6">
                  {items.map((item, j) => {
                    const text = item.replace(/^- /, '');
                    const boldMatch = text.match(/^\*\*(.+?)\*\*\s*[—–-]\s*(.+)$/);
                    return (
                      <li key={j} className="flex items-start gap-2 text-text-secondary text-sm leading-relaxed">
                        <div className="w-1.5 h-1.5 rounded-full bg-brand mt-2 flex-shrink-0" />
                        {boldMatch ? (
                          <span>
                            <strong className="text-white">{boldMatch[1]}</strong> — {boldMatch[2]}
                          </span>
                        ) : (
                          <span>{text}</span>
                        )}
                      </li>
                    );
                  })}
                </ul>
              );
            }
            if (/^\d+\.\s/.test(trimmed)) {
              const items = trimmed.split('\n').filter((l) => /^\d+\.\s/.test(l));
              return (
                <ol key={i} className="space-y-2 mb-6">
                  {items.map((item, j) => (
                    <li key={j} className="flex items-start gap-3 text-text-secondary text-sm leading-relaxed">
                      <span className="text-brand font-display font-semibold text-xs mt-0.5">{j + 1}</span>
                      <span>{item.replace(/^\d+\.\s/, '')}</span>
                    </li>
                  ))}
                </ol>
              );
            }
            return (
              <p key={i} className="text-text-secondary text-sm leading-relaxed mb-4">
                {trimmed}
              </p>
            );
          })}
        </div>
      ) : (
        <div className="rounded-2xl border border-white/10 bg-bg-secondary p-8 text-center mt-8">
          <div className="w-12 h-12 rounded-xl bg-brand/10 flex items-center justify-center mx-auto mb-4">
            <span className="text-brand text-lg">📄</span>
          </div>
          <h3 className="font-display font-semibold text-lg mb-2">Coming Soon</h3>
          <p className="text-text-tertiary text-sm max-w-md mx-auto">
            This documentation page is being written. Check back soon or contribute on{' '}
            <a href={brand.social.github} className="text-brand hover:underline">
              GitHub
            </a>
            .
          </p>
        </div>
      )}
    </article>
  );
}
