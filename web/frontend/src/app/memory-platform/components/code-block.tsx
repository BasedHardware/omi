import CopyButton from './copy-button';

interface CodeBlockProps {
  code: string;
  caption?: string;
  language?: string;
}

export default function CodeBlock({ code, caption, language = 'bash' }: CodeBlockProps) {
  return (
    <figure className="overflow-hidden rounded-xl border border-white/10 bg-[#0d0d0d]">
      <div className="flex items-center justify-between border-b border-white/10 px-4 py-2">
        <span className="font-mono text-[11px] uppercase tracking-[0.14em] text-neutral-500">
          {caption ?? language}
        </span>
        <CopyButton value={code} />
      </div>
      <pre className="overflow-x-auto px-4 py-4 font-mono text-[13px] leading-relaxed text-neutral-200">
        <code>{code}</code>
      </pre>
    </figure>
  );
}
