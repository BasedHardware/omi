import { describe, expect, it, vi } from 'vitest';
import {
  clearRetiredExperimentalFeaturesStorage,
  RETIRED_EXPERIMENTAL_FEATURES_KEY,
} from '../retiredExperimentalFeatures';

describe('clearRetiredExperimentalFeaturesStorage', () => {
  it('removes the retired experimental-features key', () => {
    const storage = { removeItem: vi.fn() };

    clearRetiredExperimentalFeaturesStorage(() => storage);

    expect(storage.removeItem).toHaveBeenCalledWith(RETIRED_EXPERIMENTAL_FEATURES_KEY);
    expect(storage.removeItem).toHaveBeenCalledTimes(1);
  });

  it('never throws when removeItem fails', () => {
    const storage = {
      removeItem: vi.fn(() => {
        throw new Error('storage unavailable');
      }),
    };

    expect(() => clearRetiredExperimentalFeaturesStorage(() => storage)).not.toThrow();
    expect(storage.removeItem).toHaveBeenCalledWith(RETIRED_EXPERIMENTAL_FEATURES_KEY);
  });

  it('never throws when the storage getter itself fails', () => {
    const getStorage = (): Pick<Storage, 'removeItem'> => {
      throw new DOMException('Access is denied', 'SecurityError');
    };

    expect(() => clearRetiredExperimentalFeaturesStorage(getStorage)).not.toThrow();
  });
});
