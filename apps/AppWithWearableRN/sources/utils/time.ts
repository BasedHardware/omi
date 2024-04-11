import { createBackoff } from 'teslabot';
export async function delay(milliseconds: number): Promise<void> {
    return new Promise((resolve) => {
        setTimeout(resolve, milliseconds);
    });
}

export const backoff = createBackoff({
    onError(e, failuresCount) {
        console.error(e);
    },
});