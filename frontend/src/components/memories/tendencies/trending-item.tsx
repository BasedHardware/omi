interface TrendingItemProps {
  title: string;
  count: number;
}

export default function TrendingItem({ title, count }: TrendingItemProps) {
  return (
    <div className="fle-col flex h-20 w-full cursor-pointer flex-col justify-end rounded-lg bg-zinc-800/50 p-3 transition-all hover:bg-zinc-800/75">
      <h3 className="text-sm md:text-base">{title}</h3>
      <p className="text-xs text-neutral-400 md:text-sm">{count} memories</p>
    </div>
  );
}
