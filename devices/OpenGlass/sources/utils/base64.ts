export function toBase64Image(src: Uint8Array) {
    return 'data:image/jpeg;base64,' + toBase64(src);
}

export function toBase64(src: Uint8Array) {
    const characters = Array.from(src, (byte) => String.fromCharCode(byte)).join('');
    return btoa(characters);
}