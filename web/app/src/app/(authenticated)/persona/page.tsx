'use client';

import { useEffect, useState } from 'react';
import Image from '@tschk/moonshine-next/image';
import { ExternalLink, User } from 'lucide-react';
import { getOrCreatePersona, updatePersona } from '@/lib/api';
import { useAsyncResource } from '@/hooks/useAsyncResource';
import { isPersonaPublic, personaPublicUrl, personaStatusLabel } from '@/lib/persona';
import { MixpanelManager } from '@/lib/analytics/mixpanel';

export default function PersonaPage() {
  const {
    data: persona,
    loading,
    error,
    refresh,
  } = useAsyncResource('persona', getOrCreatePersona, {
    fallbackMessage: 'Failed to load persona',
  });

  useEffect(() => {
    MixpanelManager.pageView('Persona');
  }, []);

  const [draft, setDraft] = useState<{ name: string; username: string } | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  const startEditing = () => {
    if (!persona) return;
    setSaveError(null);
    setDraft({ name: persona.name, username: persona.username ?? '' });
  };

  const save = async () => {
    if (!persona || !draft) return;
    // Send only what changed: the route claims a handle when username is
    // present and rewrites the description when the name moves.
    const updates: { name?: string; username?: string } = {};
    if (draft.name.trim() && draft.name.trim() !== persona.name) {
      updates.name = draft.name.trim();
    }
    if (draft.username.trim() && draft.username.trim() !== (persona.username ?? '')) {
      updates.username = draft.username.trim();
    }
    if (Object.keys(updates).length === 0) {
      setDraft(null);
      return;
    }

    setSaving(true);
    setSaveError(null);
    try {
      await updatePersona(persona.id, updates);
      setDraft(null);
      await refresh();
    } catch (err) {
      console.error('Failed to update persona:', err);
      setSaveError(err instanceof Error ? err.message : 'Could not save');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="mx-auto w-full max-w-2xl px-6 py-10">
      <header>
        <h1 className="text-2xl font-bold text-text-primary">Persona</h1>
        <p className="mt-1 text-sm text-text-quaternary">
          Your AI clone, trained on what Omi knows about you.
        </p>
      </header>

      {loading ? (
        <div className="mt-8 h-40 animate-pulse rounded-card border border-stroke bg-bg-raised" />
      ) : error ? (
        <p className="mt-8 rounded-control border border-error/30 bg-error/10 px-4 py-3 text-sm text-error">
          {error}
        </p>
      ) : persona ? (
        <section className="mt-8 rounded-card border border-stroke bg-bg-raised p-6">
          <div className="flex items-start gap-4">
            {persona.image ? (
              <Image
                src={persona.image}
                alt=""
                width={64}
                height={64}
                className="h-16 w-16 rounded-full object-cover"
              />
            ) : (
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-bg-tertiary">
                <User className="h-7 w-7 text-text-quaternary" />
              </div>
            )}

            <div className="min-w-0 flex-1">
              <h2 className="truncate text-lg font-medium text-text-primary">
                {persona.name}
              </h2>
              {persona.username && (
                <p className="text-sm text-text-quaternary">@{persona.username}</p>
              )}
              <span className="mt-2 inline-block rounded-full bg-bg-tertiary px-2.5 py-0.5 text-xs text-text-tertiary">
                {personaStatusLabel(persona)}
              </span>
            </div>
          </div>

          {persona.description && (
            <p className="mt-4 text-sm text-text-secondary">{persona.description}</p>
          )}

          {isPersonaPublic(persona) && persona.username && (
            <a
              href={personaPublicUrl(persona.username)}
              target="_blank"
              rel="noopener noreferrer"
              className="mt-5 inline-flex items-center gap-2 rounded-control bg-bg-tertiary px-3 py-2 text-xs text-text-secondary transition-colors hover:bg-bg-quaternary"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              View public page
            </a>
          )}

          <div className="mt-6 border-t border-stroke pt-4">
            {draft ? (
              <div className="space-y-3">
                <label className="block">
                  <span className="text-xs uppercase tracking-wide text-text-quaternary">
                    Name
                  </span>
                  <input
                    value={draft.name}
                    aria-label="Persona name"
                    maxLength={200}
                    onChange={(event) => setDraft({ ...draft, name: event.target.value })}
                    className="mt-1.5 w-full rounded-control bg-bg-tertiary px-3 py-2 text-sm text-text-primary outline-none focus:ring-1 focus:ring-text-quaternary"
                  />
                </label>
                <label className="block">
                  <span className="text-xs uppercase tracking-wide text-text-quaternary">
                    Handle
                  </span>
                  <input
                    value={draft.username}
                    aria-label="Persona handle"
                    maxLength={64}
                    onChange={(event) =>
                      setDraft({ ...draft, username: event.target.value })
                    }
                    className="mt-1.5 w-full rounded-control bg-bg-tertiary px-3 py-2 text-sm text-text-primary outline-none focus:ring-1 focus:ring-text-quaternary"
                  />
                </label>

                {saveError && <p className="text-sm text-error">{saveError}</p>}

                <p className="text-xs text-text-quaternary">
                  Changing the name rewrites the generated description.
                </p>

                <div className="flex justify-end gap-2">
                  <button
                    type="button"
                    onClick={() => setDraft(null)}
                    className="rounded-control px-4 py-2 text-sm text-text-quaternary transition-colors hover:text-text-secondary"
                  >
                    Cancel
                  </button>
                  <button
                    type="button"
                    onClick={() => void save()}
                    disabled={saving}
                    className="rounded-control bg-text-primary px-4 py-2 text-sm font-medium text-bg-primary transition-opacity hover:opacity-90 disabled:opacity-40"
                  >
                    {saving ? 'Saving…' : 'Save'}
                  </button>
                </div>
              </div>
            ) : (
              <button
                type="button"
                onClick={startEditing}
                className="rounded-control bg-bg-tertiary px-3 py-2 text-xs text-text-secondary transition-colors hover:bg-bg-quaternary"
              >
                Edit persona
              </button>
            )}
          </div>
        </section>
      ) : null}
    </div>
  );
}
