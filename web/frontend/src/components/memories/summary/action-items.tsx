import { ActionItems as ActionItemsType } from '@/src/types/memory.types';
import {
  avatarToneIndex,
  participantInitials,
  actionItemFacts,
} from '@/src/lib/shared-note.mjs';

interface ActionsItemsProps {
  items: ActionItemsType[];
}

export default function ActionItems({ items }: ActionsItemsProps) {
  return (
    <div>
      <h2 className="sn-h3">Action items</h2>
      <ul className="sn-actions">
        {items.map((item, index) => {
          const { owner, ownerKnown, context, due } = actionItemFacts(item);
          // Owner and due share one line; context gets its own. An unknown owner or due
          // date is left out rather than spelled "Unknown".
          const hasMeta = ownerKnown || Boolean(due);
          return (
            <li
              key={index}
              className={`sn-action${item.completed ? ' sn-action-done' : ''}`}
            >
              <span className="sn-checkbox" aria-hidden="true" />
              <span className="sn-sr">
                {item.completed ? 'Completed' : 'Not completed'}
              </span>
              <div className="sn-action-body">
                <p className="sn-action-text">{item.description}</p>
                {hasMeta && (
                  <div className="sn-action-meta">
                    {ownerKnown && (
                      <span className="sn-owner">
                        <span
                          className={`sn-avatar sn-avatar-${avatarToneIndex(owner)}`}
                          aria-hidden="true"
                        >
                          {participantInitials(owner)}
                        </span>
                        {owner}
                      </span>
                    )}
                    {due && (
                      <time
                        dateTime={due.iso}
                        aria-label={
                          due.certainty === 'tentative'
                            ? `Tentatively due ${due.label}`
                            : undefined
                        }
                      >
                        Due {due.certainty === 'tentative' ? '~' : ''}
                        {due.label}
                      </time>
                    )}
                  </div>
                )}
                {context && <p className="sn-context">{context}</p>}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
