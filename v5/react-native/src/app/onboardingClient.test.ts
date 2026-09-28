import type {OmiBackend} from '../omiNative';
import {
  parseAvailableLanguages,
  saveAcquisitionSource,
  saveOnboardingCompleted,
  savePrimaryLanguage,
} from './onboardingClient';

test('parseAvailableLanguages keeps server order', () => {
  expect(
    parseAvailableLanguages(
      {
        languages: [
          {code: 'ja', name: 'Japanese'},
          {code: 'en', name: 'English'},
        ],
      },
      'languages',
    ),
  ).toEqual([
    {code: 'ja', name: 'Japanese'},
    {code: 'en', name: 'English'},
  ]);
});

test('setup writes go through native HTTP and stay no-ops without a backend', async () => {
  const request = jest.fn(async (value: {id: string}) => ({
    id: value.id,
    status: 200,
    body: JSON.stringify({status: 'ok', single_language_mode: true}),
  }));
  const backend = {
    request,
    generationEvents: jest.fn(),
    cancelGenerationEvents: jest.fn(),
  } as unknown as OmiBackend;

  await savePrimaryLanguage(undefined, 'ja');
  await saveAcquisitionSource(null, 'TikTok');
  await saveOnboardingCompleted(undefined);
  expect(request).not.toHaveBeenCalled();

  await savePrimaryLanguage(backend, 'ja');
  await saveAcquisitionSource(backend, 'TikTok');
  await saveOnboardingCompleted(backend);

  expect(request).toHaveBeenNthCalledWith(1, {
    id: 'onboarding-language-write',
    method: 'PATCH',
    path: '/v1/users/language',
    body: JSON.stringify({language: 'ja'}),
    headers: {'Content-Type': 'application/json'},
  });
  expect(request).toHaveBeenNthCalledWith(2, {
    id: 'onboarding-source-write',
    method: 'PATCH',
    path: '/v1/users/onboarding',
    body: JSON.stringify({acquisition_source: 'TikTok'}),
    headers: {'Content-Type': 'application/json'},
  });
  expect(request).toHaveBeenNthCalledWith(3, {
    id: 'onboarding-complete-write',
    method: 'PATCH',
    path: '/v1/users/onboarding',
    body: JSON.stringify({completed: true}),
    headers: {'Content-Type': 'application/json'},
  });
});

test('a failed completion write does not reject local setup', async () => {
  const request = jest.fn(async () => {
    throw new Error('offline');
  });
  const backend = {
    request,
    generationEvents: jest.fn(),
    cancelGenerationEvents: jest.fn(),
  } as unknown as OmiBackend;
  await expect(saveOnboardingCompleted(backend)).resolves.toBeUndefined();
});
