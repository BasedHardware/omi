import * as React from 'react';
import { HappyError } from '../../modules/errors/HappyError';
import { alert } from './alert';

export function useHappyAction(action: () => Promise<void>) {
    const [loading, setLoading] = React.useState(false);
    const loadingRef = React.useRef(false);
    const doAction = React.useCallback(() => {
        if (loadingRef.current) {
            return;
        }
        loadingRef.current = true;
        setLoading(true);
        (async () => {
            try {
                while (true) {
                    try {
                        await action();
                        break;
                    } catch (e) {
                        if (e instanceof HappyError) {
                            if (e.canTryAgain) {
                                if (await alert('Error', e.message, [{ text: 'Try again' }, { text: 'Cancel', style: 'cancel' }]) !== 0) {
                                    break;
                                }
                            } else {
                                await alert('Error', e.message, [{ text: 'Cancel', style: 'cancel' }]);
                                break;
                            }
                        } else {
                            await alert('Error', 'Unknown error', [{ text: 'Cancel', style: 'cancel' }]);
                            break;
                        }
                    }
                }
            } finally {
                loadingRef.current = false;
                setLoading(false);
            }
        })();
    }, [action]);
    return [loading, doAction] as const;
}