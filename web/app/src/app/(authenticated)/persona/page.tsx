'use client';

import { useCallback, useEffect, useState } from 'react';
import Image from 'next/image';
import { ExternalLink, User } from 'lucide-react';
import { getOrCreatePersona } from '@/lib/api';
import { isPersonaPublic, personaPublicUrl, personaStatusLabel } from '@/lib/persona';
import { MixpanelManager } from '@/lib/analytics/mixpanel';
import type { App } from '@/types/apps';

export default function PersonaPage() {
  const [persona, setPersona] = useState<App | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    MixpanelManager.pageView('Persona');
  }, []);

  const load = useCallback(async (isMounted: () => boolean) => {
    try {
      const loaded = await getOrCreatePersona();
      if (!isMounted()) return;
      setPersona(loaded);
      setError(null);
    } catch (err) {
      console.error('Failed to load persona:', err);
      if (!isMounted()) return;
      setError(err instanceof Error ? err.message : 'Failed to load persona');
    } finally {
      if (isMounted()) setLoading(false);
    }
  }, []);

  useEffect(() => {
    let mounted = true;
    void load(() => mounted);
    return () => {
      mounted = false;
    };
  }, [load]);

  return (
    <div className="mx-auto w-full max-w-2xl px-6 py-10">
      <header>
        <h1 className="text-2xl font-bold text-text-primary">Persona</h1>
        <p className="mt-1 text-sm text-text-quaternary">
          Your AI clone, trained on what Omi knows about you.
        </p>
      </header>

      {loading ? (
        <div className="mt-8 h-40 animate-pulse rounded-xl border border-bg-tertiary bg-bg-secondary" />
      ) : error ? (
        <p className="mt-8 rounded-lg border border-error/30 bg-error/10 px-4 py-3 text-sm text-error">
          {error}
        </p>
      ) : persona ? (
        <section className="mt-8 rounded-xl border border-bg-tertiary bg-bg-secondary p-6">
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
              className="mt-5 inline-flex items-center gap-2 rounded-lg bg-bg-tertiary px-3 py-2 text-xs text-text-secondary transition-colors hover:bg-bg-quaternary"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              View public page
            </a>
          )}

          <p className="mt-6 border-t border-bg-tertiary pt-4 text-xs text-text-quaternary">
            Editing your persona is available in the Omi desktop and mobile apps.
          </p>
        </section>
      ) : null}
    </div>
  );
}
