import { ActionItems as ActionItemsType } from '@/src/types/memory.types';
import { avatarToneIndex, participantInitials } from '@/src/lib/shared-note.mjs';
import moment from 'moment';

interface ActionsItemsProps {
  items: ActionItemsType[];
}

export default function ActionItems({ items }: ActionsItemsProps) {
  return (
    <div>
      <h2 className="sn-h3">Action items</h2>
      <ul className="sn-actions">
        {items.map((item, index) => {
          const owner = typeof item.owner_name === 'string' ? item.owner_name.trim() : '';
          const context = typeof item.context === 'string' ? item.context.trim() : '';
          const due = item.due_at ? moment(item.due_at) : null;
          const dueLabel = due && due.isValid() ? due.format('MMM D, YYYY') : '';
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
                {(owner || context || dueLabel) && (
                  <div className="sn-action-meta">
                    {owner && (
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
                    {context && <span className="sn-context">{context}</span>}
                    {dueLabel && <span>Due {dueLabel}</span>}
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
