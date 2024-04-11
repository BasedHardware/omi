import * as React from 'react';
import { PrimitiveAtom, atom, useAtomValue } from 'jotai';
import { SuperClient } from "../api/client";
import { storage } from '../../storage';
import { AsyncLock, InvalidateSync } from 'teslabot';
import { Jotai } from './_types';
import { backoff } from '../../utils/time';

export type ViewSession = {
    id: string,
    index: number,
    state: 'starting' | 'processing' | 'finished' | 'canceled' | 'in-progress',
    audio: {
        duration: number,
        size: number
    } | null
};

export type ViewSessionFull = {
    id: string,
    index: number,
    state: 'starting' | 'processing' | 'finished' | 'canceled' | 'in-progress',
    audio: {
        duration: number,
        size: number
    } | null,
    text: string | null
};

export class SessionsModel {
    readonly client: SuperClient;
    readonly sessions = atom<ViewSession[] | null>(null);
    readonly jotai: Jotai;
    #fullSessions = new Map<string, PrimitiveAtom<ViewSessionFull | null>>();
    #fullSessionsLock = new AsyncLock();
    #sessions: ViewSession[] | null = null;
    #refresh: InvalidateSync

    constructor(client: SuperClient, jotai: Jotai) {
        this.client = client;
        this.jotai = jotai;

        // Load initial
        let ex = storage.getString('sessions');
        if (ex) {
            this.#sessions = JSON.parse(ex);
            this.jotai.set(this.sessions, this.#filter(this.#sessions!));
        }

        // Refresh
        this.#refresh = new InvalidateSync(async () => {
            let loaded = await this.client.listSessions();
            this.#applySessions(loaded.sessions.map((v) => ({ id: v.id, index: v.index, state: v.state, audio: v.audio })));
        });
    }

    #applySessions = (sessions: ViewSession[]) => {

        // Collect updated IDs
        let updated = new Set<string>();
        for (let session of sessions) {
            updated.add(session.id);
        }

        // Merge
        let merged = [...sessions, ...(this.#sessions || [])!.filter(s => !updated.has(s.id))];
        merged.sort((a, b) => b.index - a.index);

        // Merge to full sessions too
        for (let session of sessions) {
            let s = this.#fullSessions.get(session.id);
            if (!s) {
                continue;
            }
            let v = this.jotai.get(s);
            if (v) {
                this.jotai.set(s, { ...v, ...session });
            }
        }

        // Update
        this.#sessions = merged;
        storage.set('sessions', JSON.stringify(this.#sessions));
        this.jotai.set(this.sessions, this.#filter(this.#sessions!));
    }

    #filter = (sessions: ViewSession[]) => {
        return sessions.filter(s => s.state !== 'canceled');
    }

    apply = (session: ViewSession) => {
        this.#applySessions([session]);
    }

    applyPartial = (session: Partial<ViewSession>) => {
        let s = this.#sessions?.find(s => s.id === session.id);
        if (!s) {
            return;
        }
        this.apply({ ...s, ...session });
    }

    applyPartialFull = (session: Partial<ViewSessionFull>) => {
        let s = this.#fullSessions.get(session.id!);
        if (!s) {
            return;
        }
        let v = this.jotai.get(s);
        if (v) {
            this.jotai.set(s, { ...v, ...session });
        }
    }

    invalidate = () => {
        this.#refresh.invalidate();
    }

    use = () => {
        return useAtomValue(this.sessions);
    }

    useFull = (id: string) => {
        let fatom = this.#fullSessions.get(id);
        if (!fatom) {
            fatom = atom<ViewSessionFull | null>(null);
            this.#fullSessions.set(id, fatom);
        }
        React.useEffect(() => {
            this.#fullSessionsLock.inLock(async () => {
                let res = await this.client.getFullSession(id);
                this.jotai.set(fatom!, {
                    id: res.session.id,
                    index: res.session.index,
                    state: res.session.state,
                    audio: res.session.audio,
                    text: res.session.text
                });
            });
        }, []);
        return useAtomValue(fatom);
    }
}