/**
 * OMI Web App - Safe Vocabulary List Persistence Handler
 * Issue #15243: Fix vocabulary word addition resetting saved list
 * Author: Hasnain Chavhan (@HasnainChavhan)
 */

export interface VocabWord {
  id: string;
  word: string;
  definition: string;
  created_at: string;
}

export function addVocabWordSafely(
  existingList: VocabWord[],
  newWord: VocabWord
): VocabWord[] {
  // Prevent duplicate insertion and preserve existing items
  const exists = existingList.some(item => item.id === newWord.id || item.word.toLowerCase() === newWord.word.toLowerCase());
  if (exists) {
    return existingList;
  }
  return [...existingList, newWord];
}
