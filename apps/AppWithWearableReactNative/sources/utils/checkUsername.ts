export function checkUsername(src: string) {
    if (src.length < 5) {
        return false;
    }
    if (src.length > 16) {
        return false;
    }
    if (!/^\w*$/.test(src)) {
        return false;
    }
    return true;
}