'use client';
import * as Popover from '@radix-ui/react-popover';
import { usePathname, useSearchParams } from 'next/navigation';
import { useRouter } from 'next/navigation';

const categories = [
  { icon: '🌟', value: 'inspiration', label: 'Inspiration' },
  { icon: '👥', value: 'personal', label: 'Personal' },
  { icon: '💼', value: 'work', label: 'Work' },
  { icon: '🎉', value: 'celebrations', label: 'Celebrations' },
  { icon: '🚀', value: 'travel', label: 'Travel' },
  { icon: '🎨', value: 'art', label: 'Art' },
  { icon: '📚', value: 'books', label: 'Books' },
  { icon: '🎵', value: 'music', label: 'Music' },
  { icon: '🎬', value: 'movies', label: 'Movies' },
  { icon: '👩‍👩‍👧‍👦', value: 'family', label: 'Family' },
  { icon: '👫', value: 'friends', label: 'Friends' },
  { icon: '🚫', value: 'memories', label: 'Memories' },
  { icon: '🚪', value: 'places', label: 'Places' },
  { icon: '🚫', value: 'events', label: 'Events' },
  { icon: '🚫', value: 'milestones', label: 'Milestones' },
  { icon: '🚫', value: 'achievements', label: 'Achievements' },
  { icon: '🚫', value: 'goals', label: 'Goals' },
  { icon: '🚫', value: 'quotes', label: 'Quotes' },
  { icon: '🚫', value: 'jokes', label: 'Jokes' },
  { icon: '🚫', value: 'poems', label: 'Poems' },
  { icon: '🚫', value: 'stories', label: 'Stories' },
  { icon: '🚫', value: 'recipes', label: 'Recipes' },
  { icon: '🚫', value: 'diy', label: 'DIY' },
  { icon: '🚫', value: 'fitness', label: 'Fitness' },
  { icon: '🚫', value: 'health', label: 'Health' },
  { icon: '🚫', value: 'beauty', label: 'Beauty' },
  { icon: '🚫', value: 'fashion', label: 'Fashion' },
  { icon: '🚫', value: 'technology', label: 'Technology' },
  { icon: '🚫', value: 'science', label: 'Science' },
  { icon: '🚫', value: 'history', label: 'History' },
  { icon: '🚫', value: 'philosophy', label: 'Philosophy' },
  { icon: '🚫', value: 'spirituality', label: 'Spirituality' },
  { icon: '🚫', value: 'self-improvement', label: 'Self-Improvement' },
  { icon: '🚫', value: 'productivity', label: 'Productivity' },
  { icon: '🚫', value: 'business', label: 'Business' },
  { icon: '🚫', value: 'finance', label: 'Finance' },
  { icon: '🚫', value: 'marketing', label: 'Marketing' },
];

export default function CategoriesDropdown() {
  const searchParams = useSearchParams();
  const pathname = usePathname();
  const router = useRouter();

  const currentCategory = searchParams.get('category') || '';

  const handleCategoryClick = (category: string) => {
    const params = new URLSearchParams(searchParams.toString());
    params.set('category', category);
    router.push(`${pathname}?${params.toString()}`);
  };

  return (
    <Popover.Root>
      <Popover.Trigger asChild>
        <button className="flex flex-nowrap gap-2 rounded-md border border-solid border-zinc-600 bg-transparent px-5 py-2">
          {currentCategory && (
            <span>{categories.find((c) => c.value === currentCategory)?.icon}</span>
          )}
          <span className="whitespace-nowrap">{currentCategory || 'All categories'}</span>
        </button>
      </Popover.Trigger>
      <Popover.Portal>
        <Popover.Content
          align="end"
          className="data-[state=open]:data-[side=top]:animate-slideDownAndFade data-[state=open]:data-[side=right]:animate-slideLeftAndFade data-[state=open]:data-[side=bottom]:animate-slideUpAndFade w-full rounded bg-white p-5 shadow-[0_10px_38px_-10px_hsla(206,22%,7%,.35),0_10px_20px_-15px_hsla(206,22%,7%,.2)] will-change-[transform,opacity] focus:shadow-[0_10px_38px_-10px_hsla(206,22%,7%,.35),0_10px_20px_-15px_hsla(206,22%,7%,.2),0_0_0_2px_theme(colors.violet7)] data-[state=open]:data-[side=left]:animate-slideRightAndFade"
          sideOffset={5}
        >
          <div className="grid grid-cols-4 gap-2.5">
            {categories.map((category) => (
              <button
                onClick={() => handleCategoryClick(category.value)}
                key={category.value}
                className="flex items-center gap-2.5 px-1.5 py-1.5 text-base"
                aria-label={category.label}
              >
                <span>{category.icon}</span>
                <span>{category.label}</span>
              </button>
            ))}
          </div>
          <Popover.Close
            className="text-violet11 hover:bg-violet4 focus:shadow-violet7 absolute right-[5px] top-[5px] inline-flex h-[25px] w-[25px] cursor-default items-center justify-center rounded-full outline-none focus:shadow-[0_0_0_2px]"
            aria-label="Close"
          >
            x
          </Popover.Close>
          <Popover.Arrow className="fill-white" />
        </Popover.Content>
      </Popover.Portal>
    </Popover.Root>
  );
}
