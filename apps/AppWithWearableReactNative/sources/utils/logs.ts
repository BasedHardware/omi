export function log(tag: string, src: string) {
    if (__DEV__) {
        console.log('[' + tag + ']: ' + src);
    }
}