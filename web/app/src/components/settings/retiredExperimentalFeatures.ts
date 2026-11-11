export const RETIRED_EXPERIMENTAL_FEATURES_KEY = 'omi_experimental_features';

export function clearRetiredExperimentalFeaturesStorage(
  getStorage: () => Pick<Storage, 'removeItem'>,
): void {
  try {
    getStorage().removeItem(RETIRED_EXPERIMENTAL_FEATURES_KEY);
  } catch {}
}
