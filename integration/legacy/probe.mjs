import { QA_BEARER_TOKEN } from './constants.mjs';

/**
 * @typedef {{ name: string, ok: boolean, servedRequests: number, failure?: string }} DomainProbeResult
 */

/**
 * @param {unknown} value
 * @param {string} label
 */
function assertObject(value, label) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error(`${label} is not an object`);
  }
}

/**
 * @param {Response} response
 */
async function readJson(response) {
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch {
    throw new Error(`response body is not JSON (${text.slice(0, 80)})`);
  }
}

/**
 * @param {string} baseUrl
 * @param {string} token
 */
async function fetchStatus(baseUrl, token) {
  const response = await fetch(`${baseUrl}/__qa/status`, {
    headers: { authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error(`status probe HTTP ${response.status}`);
  }
  const body = await readJson(response);
  if (typeof body.hitCount !== 'number') {
    throw new Error('status probe missing numeric hitCount');
  }
  return body.hitCount;
}

/**
 * @param {unknown} body
 */
export function assertActionItemsShape(body) {
  assertObject(body, 'action-items');
  if (!Array.isArray(body.action_items) || body.action_items.length === 0) {
    throw new Error('action-items missing non-empty action_items array');
  }
  for (const item of body.action_items) {
    assertObject(item, 'action-item');
    if (typeof item.id !== 'string' || item.id.length === 0) {
      throw new Error('action-item missing string id');
    }
    if (typeof item.description !== 'string') {
      throw new Error(`action-item ${item.id} missing description`);
    }
    if (typeof item.completed !== 'boolean') {
      throw new Error(`action-item ${item.id} missing completed boolean`);
    }
    if (!('created_at' in item) || !('updated_at' in item)) {
      throw new Error(`action-item ${item.id} missing timestamp fields`);
    }
  }
}

/**
 * @param {unknown} body
 */
export function assertActionItemIdsShape(body) {
  assertObject(body, 'action-item-ids');
  if (!Array.isArray(body.ids) || body.ids.length === 0) {
    throw new Error('action-item ids missing non-empty ids array');
  }
  for (const id of body.ids) {
    if (typeof id !== 'string' || id.length === 0) {
      throw new Error('action-item ids contains non-string id');
    }
  }
}

/**
 * @param {unknown} body
 */
export function assertConversationsShape(body) {
  if (!Array.isArray(body) || body.length === 0) {
    throw new Error('conversations response is not a non-empty array');
  }
  for (const row of body) {
    assertObject(row, 'conversation');
    if (typeof row.id !== 'string' || row.id.length === 0) {
      throw new Error('conversation missing string id');
    }
    if (!row.structured || typeof row.structured !== 'object') {
      throw new Error(`conversation ${row.id} missing structured object`);
    }
    if (typeof row.structured.title !== 'string' || row.structured.title.length === 0) {
      throw new Error(`conversation ${row.id} missing structured.title`);
    }
    if (typeof row.status !== 'string') {
      throw new Error(`conversation ${row.id} missing status`);
    }
  }
}

/**
 * @param {unknown} body
 */
export function assertFoldersShape(body) {
  if (!Array.isArray(body) || body.length === 0) {
    throw new Error('folders response is not a non-empty array');
  }
  for (const row of body) {
    assertObject(row, 'folder');
    if (typeof row.id !== 'string' || row.id.length === 0) {
      throw new Error('folder missing string id');
    }
    if (typeof row.name !== 'string' || row.name.length === 0) {
      throw new Error(`folder ${row.id} missing name`);
    }
    if (typeof row.is_default !== 'boolean' || typeof row.is_system !== 'boolean') {
      throw new Error(`folder ${row.id} missing default/system flags`);
    }
  }
}

/**
 * @param {string} baseUrl
 * @param {string} path
 * @param {string} token
 */
async function legacyGet(baseUrl, path, token) {
  const response = await fetch(`${baseUrl}${path}`, {
    headers: { authorization: `Bearer ${token}` },
  });
  if (!response.ok) {
    throw new Error(`GET ${path} HTTP ${response.status}`);
  }
  return readJson(response);
}

/**
 * Probe legacy-wire domains (tasks/action-items, conversations, folders).
 *
 * @param {{ baseUrl: string, token?: string }} options
 * @returns {Promise<DomainProbeResult[]>}
 */
export async function probeLegacyDomains(options) {
  const { baseUrl } = options;
  const token = options.token ?? QA_BEARER_TOKEN;

  /** @type {DomainProbeResult[]} */
  const results = [];

  async function probeDomain(name, work) {
    let before = 0;
    try {
      before = await fetchStatus(baseUrl, token);
    } catch (err) {
      results.push({
        name,
        ok: false,
        servedRequests: 0,
        failure: err instanceof Error ? err.message : String(err),
      });
      return;
    }

    try {
      await work();
      const after = await fetchStatus(baseUrl, token);
      const servedRequests = after - before;
      if (servedRequests <= 0) {
        results.push({
          name,
          ok: false,
          servedRequests: Math.max(0, servedRequests),
          failure: `expected domain traffic on ${name} but hitCount delta was ${servedRequests}`,
        });
        return;
      }
      results.push({ name, ok: true, servedRequests });
    } catch (err) {
      const after = await fetchStatus(baseUrl, token).catch(() => before);
      const servedRequests = Math.max(0, after - before);
      results.push({
        name,
        ok: false,
        servedRequests,
        failure: err instanceof Error ? err.message : String(err),
      });
    }
  }

  await probeDomain('tasks', async () => {
    const list = await legacyGet(baseUrl, '/v1/action-items', token);
    assertActionItemsShape(list);
    const ids = await legacyGet(baseUrl, '/v1/action-items/ids', token);
    assertActionItemIdsShape(ids);
    const listIds = new Set(list.action_items.map((row) => row.id));
    for (const id of ids.ids) {
      if (!listIds.has(id)) {
        throw new Error(`action-item id ${id} missing from list payload`);
      }
    }
  });

  await probeDomain('conversations', async () => {
    const rows = await legacyGet(baseUrl, '/v1/conversations', token);
    assertConversationsShape(rows);
  });

  await probeDomain('folders', async () => {
    const rows = await legacyGet(baseUrl, '/v1/folders', token);
    assertFoldersShape(rows);
  });

  return results;
}
