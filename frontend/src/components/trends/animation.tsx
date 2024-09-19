'use client';

export default function Animation({ children }: { children: React.ReactNode }) {
  return (
    <div className="mx-auto mt-32 flex max-w-screen-sm flex-col gap-10">{children}</div>
  );
}
