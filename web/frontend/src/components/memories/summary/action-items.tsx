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
          const { owner, context, due } = actionItemFacts(item);
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
                <div className="sn-action-meta">
                  {owner && (
                    <span className="sn-owner">
                      <span
                        className={`sn-avatar sn-avatar-${avatarToneIndex(owner)}`}
                        aria-hidden="true"
                      >
                        {participantInitials(owner)}
                      </span>
                      Owner: {owner}
                    </span>
                  )}
                  {context && <span className="sn-context">{context}</span>}
                  {due ? (
                    <time dateTime={due.iso}>Due {due.label}</time>
                  ) : (
                    <span>Due Unknown</span>
                  )}
                </div>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
