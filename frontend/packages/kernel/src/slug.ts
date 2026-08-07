import { SLUG_WORDS_PER_USER_DOMAIN, parseRecordId, type RecordId } from "@omi-core/contracts";

/**
 * Slug generation — ADR-006. The wordlist is a versioned, append-only
 * artifact; this starter list is version 1 and grows via codegen, never by
 * inline edits (append-only: removing or reordering words changes nothing for
 * existing ids but editing history must stay auditable).
 *
 * Curation rules: 2–12 lowercase ASCII letters; no confusable pairs, no
 * profanity-adjacent combinations, concrete imageable words preferred.
 */
export const WORDLIST_VERSION = 1;

// prettier-ignore
export const WORDLIST: readonly string[] = [
  "amber","anchor","apple","arrow","aspen","atlas","autumn","badger","bamboo","basil",
  "beacon","berry","birch","bison","blossom","breeze","bridge","bronze","brook","butter",
  "canyon","carbon","cedar","cello","chalk","cherry","cinder","citrus","clover","cobalt",
  "comet","copper","coral","cosmos","cotton","cricket","crimson","crystal","cypress","daisy",
  "dawn","delta","denim","dragon","drift","eagle","ember","falcon","feather","fern",
  "fig","finch","fjord","flame","flint","forest","fossil","fox","frost","galaxy",
  "garden","garnet","ginger","glacier","goose","granite","grape","grove","harbor","hazel",
  "heron","hickory","honey","horizon","ibis","indigo","iris","iron","island","ivory",
  "jade","jasper","juniper","kelp","kite","lagoon","lantern","larch","lark","lava",
  "lemon","lilac","linen","lotus","lunar","magnet","mango","maple","marble","meadow",
  "mesa","meteor","mint","mirror","molar","moss","moth","mountain","mulberry","nectar",
  "nickel","north","nutmeg","oak","ocean","olive","onyx","opal","orchid","osprey",
  "otter","owl","panda","paper","peach","pearl","pebble","pecan","penguin","peony",
  "pepper","petal","pine","pistachio","planet","plum","pond","poplar","prairie","prism",
  "pumpkin","quartz","quill","rain","raven","reef","ridge","river","robin","rocket",
  "rose","rowan","ruby","rust","saffron","sage","salmon","sand","sapphire","satin",
  "sequoia","shadow","shell","sierra","silver","sky","slate","smoke","snow","solar",
  "sparrow","spice","spruce","squid","star","stone","storm","summer","sunset","swan",
  "tangerine","teal","tempo","thistle","thunder","tiger","timber","topaz","trellis","trout",
  "tulip","tundra","turquoise","velvet","vibrant","violet","walnut","wave","willow","winter",
  "wolf","wren","zephyr","zinc",
];

/** Deterministic given the rng — inject a seeded rng in tests. */
export function generateSlug(rng: () => number, words = SLUG_WORDS_PER_USER_DOMAIN): RecordId {
  const parts: string[] = [];
  for (let i = 0; i < words; i++) {
    const idx = Math.floor(rng() * WORDLIST.length) % WORDLIST.length;
    parts.push(WORDLIST[idx]!);
  }
  const parsed = parseRecordId(parts.join("-"));
  if (!parsed) throw new Error("wordlist produced an invalid slug — curation rule violated");
  return parsed.id;
}
