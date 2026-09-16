import type {OmiBackend} from '../omiNative';

export type AvailableLanguage = {
  code: string;
  name: string;
};

function object(value: unknown, label: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${label} is malformed`);
  }
  return value as Record<string, unknown>;
}

function optionalString(value: unknown): string | null {
  return typeof value === 'string' && value.length > 0 ? value : null;
}

async function cloudRequest(
  backend: OmiBackend,
  id: string,
  method: 'GET' | 'POST' | 'PATCH',
  path: `/${string}`,
  body?: string,
): Promise<unknown> {
  const response = await new Promise<
    Awaited<ReturnType<OmiBackend['request']>>
  >((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`${id} timed out`));
    }, 2500);
    backend
      .request({
        id,
        method,
        path,
        ...(body === undefined
          ? {}
          : {body, headers: {'Content-Type': 'application/json'}}),
      })
      .then(value => {
        clearTimeout(timer);
        resolve(value);
      })
      .catch(error => {
        clearTimeout(timer);
        reject(error);
      });
  });
  if (response.status === 401) {
    const unauthorized = new Error('Sign in required') as Error & {
      code: string;
    };
    unauthorized.code = 'unauthorized';
    throw unauthorized;
  }
  if (response.status !== 200) {
    throw new Error(`${id} failed (${response.status})`);
  }
  if (response.body === null) {
    throw new Error(`${id} returned an empty response`);
  }
  try {
    return JSON.parse(response.body) as unknown;
  } catch {
    throw new Error(`${id} returned invalid JSON`);
  }
}

export function parseAvailableLanguages(
  value: unknown,
  label: string,
): AvailableLanguage[] {
  const record = object(value, label);
  if (!Array.isArray(record.languages)) {
    throw new Error(`${label} is malformed`);
  }
  return record.languages.map((entry, index) => {
    const language = object(entry, `${label} item ${index}`);
    const code = optionalString(language.code);
    const name = optionalString(language.name);
    if (code === null || name === null) {
      throw new Error(`${label} item ${index} is malformed`);
    }
    return {code, name};
  });
}

export async function loadAvailableLanguages(
  backend: OmiBackend | null | undefined,
): Promise<AvailableLanguage[] | null> {
  if (backend == null) {
    return null;
  }
  try {
    return parseAvailableLanguages(
      await cloudRequest(
        backend,
        'onboarding-languages-read',
        'GET',
        '/v1/users/available-languages',
      ),
      'Available languages',
    );
  } catch {
    return null;
  }
}

export async function savePrimaryLanguage(
  backend: OmiBackend | null | undefined,
  language: string,
): Promise<void> {
  if (backend == null) {
    return;
  }
  try {
    const body = await cloudRequest(
      backend,
      'onboarding-language-write',
      'PATCH',
      '/v1/users/language',
      JSON.stringify({language}),
    );
    const record = object(body, 'Language update');
    if (record.status !== 'ok') {
      throw new Error('Language could not be saved');
    }
  } catch {
    // Browser and unsigned sessions still have to leave this card.
  }
}

export async function saveAcquisitionSource(
  backend: OmiBackend | null | undefined,
  source: string,
): Promise<void> {
  if (backend == null) {
    return;
  }
  try {
    const body = await cloudRequest(
      backend,
      'onboarding-source-write',
      'PATCH',
      '/v1/users/onboarding',
      JSON.stringify({acquisition_source: source}),
    );
    const record = object(body, 'Onboarding source update');
    if (record.status !== 'ok') {
      throw new Error('Could not save how you found Omi');
    }
  } catch {
    // Browser and unsigned sessions still have to leave this card.
  }
}

export async function saveOnboardingCompleted(
  backend: OmiBackend | null | undefined,
): Promise<void> {
  if (backend == null) {
    return;
  }
  try {
    const body = await cloudRequest(
      backend,
      'onboarding-complete-write',
      'PATCH',
      '/v1/users/onboarding',
      JSON.stringify({completed: true}),
    );
    const record = object(body, 'Onboarding completion');
    if (record.status !== 'ok') {
      throw new Error('Setup could not be saved');
    }
  } catch {
    // Local completion still has to land: a missing or failing cloud write
    // must not strand first-run on the last card after consent.
  }
}
