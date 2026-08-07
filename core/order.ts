/**
 * The default-locale collator, constructed once.
 *
 * `left.localeCompare(right)` is specified (ECMA-402) to behave exactly as
 * `new Intl.Collator().compare(left, right)`: same default locale, same default
 * options, same ordering. But JSC resolves and canonicalizes the default locale
 * on EVERY call. A sample of the live v7 GLM lane found the main thread spending
 * effectively all of its time under uloc_toLanguageTag / ulocimp_canonicalize /
 * ulocimp_getSubtags, reached from the adjacency, walk and trajectory sorts --
 * and every one of those calls allocates ICU CharStrings through the JSC
 * allocator, which does not return them to the OS.
 *
 * Hoisting the collator is therefore output-preserving by specification while
 * removing both the CPU and the allocation churn. Use it for every comparison on
 * the whole-graph path; the ordering it produces is byte-for-byte the ordering
 * `localeCompare` produced.
 */
export const compareStrings: (left: string, right: string) => number = new Intl.Collator().compare;
