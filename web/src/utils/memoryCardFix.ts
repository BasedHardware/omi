/**
 * OMI Web App - Memory Card Deletion Resilience Handler
 * Issue #15251: Fix card stuck in UI when memory deletion API fails
 * Author: Hasnain Chavhan (@HasnainChavhan)
 */

export interface MemoryItem {
  id: string;
  content: string;
  created_at: string;
}

export async function deleteMemoryCardWithFallback(
  memoryId: string,
  deleteApiFn: (id: string) => Promise<boolean>,
  onSuccess: (id: string) => void,
  onError: (id: string, err: Error) => void
): Promise<void> {
  try {
    const success = await deleteApiFn(memoryId);
    if (success) {
      onSuccess(memoryId);
    } else {
      throw new Error("Failed memory delete response from server");
    }
  } catch (error) {
    // Revert optimistic UI removal and show non-blocking toast warning
    onError(memoryId, error instanceof Error ? error : new Error(String(error)));
  }
}
