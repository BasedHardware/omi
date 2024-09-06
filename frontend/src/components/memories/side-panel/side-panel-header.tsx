import { Enlarge, Xmark } from 'iconoir-react';
import Link from 'next/link';

interface SidePanelHeaderProps {
  handleOpen: (value: boolean) => void;
  previewId: string | undefined;
}

export default function SidePanelHeader({ handleOpen, previewId }: SidePanelHeaderProps) {
  return (
    <header className={`z-[60] sticky top-0 md:-top-5 flex w-full gap-2 px-4 pt-4 md:px-12 md:pt-10 backdrop-blur-md pb-4`}>
      <button
        onClick={() => handleOpen(false)}
        className="rounded-md p-1 hover:bg-zinc-800 bg-zinc-900/50"
      >
        <Xmark className="text-base" />
      </button>
      <Link href={`/memories/${previewId}`} className="rounded-md p-1 hover:bg-zinc-800 ">
        <Enlarge className="text-base" />
      </Link>
    </header>
  );
}
