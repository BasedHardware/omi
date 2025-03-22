'use client';

import { predefinedColors } from '@/src/constants/colors';
import { TranscriptSegment } from '@/src/types/memory.types';
import { UserCircle, UserStar } from 'iconoir-react';
import { useState } from 'react';

export default function TranscriptionSegment({
  segment,
}: {
  segment: TranscriptSegment;
}) {
  const color = predefinedColors[segment.speaker_id % predefinedColors.length];
  const [showMore, setShowMore] = useState(false);

  const textFormatted =
    segment.text.replace(`Speaker ${segment.speaker_id}:`, '').charAt(0).toUpperCase() +
    segment.text.replace(`Speaker ${segment.speaker_id}:`, '').slice(1);

  const isUser = segment.is_user;

  return (
    <li className="my-5 flex gap-2">
      {isUser ? (
        <div className="grid h-7 min-w-7 place-items-center rounded-full bg-zinc-800">
          <UserStar className="text-xs" />
        </div>
      ) : (
        <div className="grid h-7 min-w-7 place-items-center rounded-full">
          <UserCircle className="min-w-min" color={color} />
        </div>
      )}
      <div>
        <p className="text-base font-semibold md:text-lg">
          {isUser ? `Owner` : `Speaker ${segment.speaker_id}`}
        </p>
        <p className="text-base font-extralight leading-7 md:text-lg md:leading-9">
          {showMore
            ? textFormatted
            : textFormatted.slice(0, 600) +
              (textFormatted.length > 600 ? '...' : '')}{' '}
          {segment.text.length > 600 && (
            <button
              onClick={() => setShowMore(!showMore)}
              className="inline text-blue-500 hover:underline"
            >
              {showMore ? ' Show less' : ' Show more'}
            </button>
          )}
        </p>
      </div>
    </li>
  );
}
