// src/renderer/src/components/signLanguage/signAssets.ts

export type AssetType = 'gif' | 'video' | 'image';

export interface SignAsset {
  url: string;
  type: AssetType;
}

export const SIGN_ASSETS: Record<string, SignAsset> = {
  'HELLO': {
    url: 'https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExNHpxbnoxYndiaGZ0Ync1YXJndW9yaGZ6bm9saXJmZnxleHBsY2FidXN6biZlcP12MV9pbnRlcm5hbF9naWZfYnlfaWQ&ct=g/l0HlMxa laS7LtoUvG/giphy.gif',
    type: 'gif'
  },
  'THANK YOU': {
    url: 'https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExNHpxbnoxYndiaGZ0Ync1YXJndW9yaGZ6bm9saXJmZnxleHBsY2FidXN6biZlcP12MV9pbnRlcm5hbF9naWZfYnlA handbook&ct=g/3o7TKP6I6v8v8v8v8/giphy.gif',
    type: 'gif'
  },
  'YES': {
    url: 'https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExNHpxbnoxYndiaGZ0Ync1YXJndW9yaGZ6bm9saXJmZnxleHBsY2FidXN6biZlcP12MV9pbnRlcm5hbF9naWZfYnlA handbook&ct=g/l0HlS.../giphy.gif',
    type: 'gif'
  },
  'NO': {
    url: 'https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExNHpxbnoxYndiaGZ0Ync1YXJndW9yaGZ6bm9saXJmZnxleHBsY2FidXN6biZlcP12MV9pbnRlcm5hbF9naWZfYnlA handbook&ct=g/l0HlS.../giphy.gif',
    type: 'gif'
  },
};

// High-quality human hand images for fingerspelling
export const ALPHABET_ASSETS: Record<string, SignAsset> = {
  'A': { url: 'https://www.signingsavvy.com/media/signs/alphabet/a.png', type: 'image' },
  'B': { url: 'https://www.signingsavvy.com/media/signs/alphabet/b.png', type: 'image' },
  'C': { url: 'https://www.signingsavvy.com/media/signs/alphabet/c.png', type: 'image' },
  'D': { url: 'https://www.signingsavvy.com/media/signs/alphabet/d.png', type: 'image' },
  'E': { url: 'https://www.signingsavvy.com/media/signs/alphabet/e.png', type: 'image' },
  'F': { url: 'https://www.signingsavvy.com/media/signs/alphabet/f.png', type: 'image' },
  'G': { url: 'https://www.signingsavvy.com/media/signs/alphabet/g.png', type: 'image' },
  'H': { url: 'https://www.signingsavvy.com/media/signs/alphabet/h.png', type: 'image' },
  'I': { url: 'https://www.signingsavvy.com/media/signs/alphabet/i.png', type: 'image' },
  'J': { url: 'https://www.signingsavvy.com/media/signs/alphabet/j.png', type: 'image' },
  'K': { url: 'https://www.signingsavvy.com/media/signs/alphabet/k.png', type: 'image' },
  'L': { url: 'https://www.signingsavvy.com/media/signs/alphabet/l.png', type: 'image' },
  'M': { url: 'https://www.signingsavvy.com/media/signs/alphabet/m.png', type: 'image' },
  'N': { url: 'https://www.signingsavvy.com/media/signs/alphabet/n.png', type: 'image' },
  'O': { url: 'https://www.signingsavvy.com/media/signs/alphabet/o.png', type: 'image' },
  'P': { url: 'https://www.signingsavvy.com/media/signs/alphabet/p.png', type: 'image' },
  'Q': { url: 'https://www.signingsavvy.com/media/signs/alphabet/q.png', type: 'image' },
  'R': { url: 'https://www.signingsavvy.com/media/signs/alphabet/r.png', type: 'image' },
  'S': { url: 'https://www.signingsavvy.com/media/signs/alphabet/s.png', type: 'image' },
  'T': { url: 'https://www.signingsavvy.com/media/signs/alphabet/t.png', type: 'image' },
  'U': { url: 'https://www.signingsavvy.com/media/signs/alphabet/u.png', type: 'image' },
  'V': { url: 'https://www.signingsavvy.com/media/signs/alphabet/v.png', type: 'image' },
  'W': { url: 'https://www.signingsavvy.com/media/signs/alphabet/w.png', type: 'image' },
  'X': { url: 'https://www.signingsavvy.com/media/signs/alphabet/x.png', type: 'image' },
  'Y': { url: 'https://www.signingsavvy.com/media/signs/alphabet/y.png', type: 'image' },
  'Z': { url: 'https://www.signingsavvy.com/media/signs/alphabet/z.png', type: 'image' },
};

export function getAssetForGloss(gloss: string): SignAsset | null {
  const upperGloss = gloss.toUpperCase();
  // 1. Try full phrase dictionary
  if (SIGN_ASSETS[upperGloss]) return SIGN_ASSETS[upperGloss];
  // 2. Try alphabet dictionary
  if (upperGloss.length === 1 && ALPHABET_ASSETS[upperGloss]) return ALPHABET_ASSETS[upperGloss];
  return null;
}
