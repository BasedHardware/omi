import * as React from 'react';
import { AsyncLock } from "../utils/lock";
import { imageDescription, llamaFind, summarizeDescriptions } from "./imageDescription";
import { startAudio } from '../modules/openai';

type AgentState = {
    lastDescription?: string;
    answer?: string;
    loading: boolean;
    summary?: string;
}

export class Agent {
    #lock = new AsyncLock();
    #photos: { photo: Uint8Array, description: string }[] = [];
    #state: AgentState = { loading: false };
    #stateCopy: AgentState = { loading: false };
    #stateListeners: (() => void)[] = [];

    async addPhoto(photos: Uint8Array[]) {
        await this.#lock.inLock(async () => {

            // Append photos
            let lastDescription: string | null = null;
            for (let p of photos) {
                console.log('Processing photo', p.length);
                let description = await imageDescription(p);
                console.log('Description', description);
                this.#photos.push({ photo: p, description });
                lastDescription = description;
            }

            // Update summaries
            let combined = '';
            let i = 0;
            for (let p of this.#photos) {
                combined += '\n\nImage #' + i + '\n\n';
                combined += p.description;
                i++;
            }
            if (combined !== '') {
                const summary = await summarizeDescriptions(combined);
                this.#state.summary = summary;
            }

            // Update UI
            if (lastDescription) {
                this.#state.lastDescription = lastDescription;
                this.#notify();
            }
        });
    }

    async answer(question: string) {
        try {
            startAudio()
        } catch(error) {
            console.log("Failed to start audio")
        }
        if (this.#state.loading) {
            return;
        }
        this.#state.loading = true;
        this.#notify();
        await this.#lock.inLock(async () => {
            let combined = '';
            let i = 0;
            for (let p of this.#photos) {
                combined += '\n\nImage #' + i + '\n\n';
                combined += p.description;
                i++;
            }
            let answer = await llamaFind(question, combined);
            this.#state.answer = answer;
            this.#state.loading = false;
            this.#notify();
        });
    }

    #notify = () => {
        this.#stateCopy = { ...this.#state };
        for (let l of this.#stateListeners) {
            l();
        }
    }


    use() {
        const [state, setState] = React.useState(this.#stateCopy);
        React.useEffect(() => {
            const listener = () => setState(this.#stateCopy);
            this.#stateListeners.push(listener);
            return () => {
                this.#stateListeners = this.#stateListeners.filter(l => l !== listener);
            }
        }, []);
        return state;
    }
}