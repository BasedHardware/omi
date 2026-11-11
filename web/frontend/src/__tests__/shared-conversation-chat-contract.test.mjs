import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { describe, it } from 'node:test';

const actionSource = readFileSync(
  new URL('../actions/memories/chat-with-memory.ts', import.meta.url),
  'utf8',
);
const componentSource = readFileSync(
  new URL('../components/memories/chat/chat.tsx', import.meta.url),
  'utf8',
);
const publicBuildContract = JSON.parse(
  readFileSync(
    new URL('../../../../config/public-build-contract.json', import.meta.url),
    'utf8',
  ),
);
const deployActionSource = readFileSync(
  new URL('../../../../.github/actions/deploy-public-build/action.yml', import.meta.url),
  'utf8',
);
const frontendWorkflowSource = readFileSync(
  new URL('../../../../.github/workflows/gcp_frontend.yml', import.meta.url),
  'utf8',
);

describe('public shared conversation chat frontend safety contract', () => {
  it('removes every direct OpenAI credential and request path', () => {
    assert.doesNotMatch(actionSource, /OPENAI_API_KEY|api\.openai\.com/);
    assert.match(actionSource, /Authorization:\s*`Bearer \$\{identityToken\}`/);
  });

  it('does not accept or send transcript content', () => {
    assert.doesNotMatch(actionSource, /transcript/i);
    assert.doesNotMatch(componentSource, /transcriptText/);
  });

  it('mints scoped OIDC server-side and sends the opaque HMAC subject', () => {
    assert.match(actionSource, /metadata\.google\.internal/);
    assert.match(actionSource, /Metadata-Flavor['"]?\s*:\s*['"]Google/);
    assert.match(actionSource, /createHmac\(['"]sha256['"]/);
    assert.match(actionSource, /X-Omi-Public-Chat-Subject/);
    assert.match(actionSource, /process\.env\.K_SERVICE/);
    assert.match(actionSource, /PUBLIC_SHARED_CONVERSATION_CHAT_FRONTEND_AUDIENCE/);
    assert.match(actionSource, /mintIdentityToken\(audience\)/);
    assert.match(actionSource, /x-forwarded-for/i);
    assert.match(actionSource, /isIP\(/);
    assert.match(actionSource, /\.at\(-2\)/);
    assert.match(
      actionSource,
      /POST \/v1\/conversations\/shared\/chat|\/v1\/conversations\/shared\/chat/,
    );
  });

  it('sends only the backend request contract and disables caching', () => {
    assert.match(actionSource, /conversation_id:\s*data\.conversationId/);
    assert.match(actionSource, /question:\s*data\.question/);
    assert.match(actionSource, /history:\s*data\.history/);
    assert.match(actionSource, /cache:\s*'no-store'/);
    assert.doesNotMatch(
      actionSource,
      /JSON\.stringify\([^)]*(transcript|tools|stream|messages)/s,
    );
  });

  it('maps structured limits and 503 into safe UI results', () => {
    assert.match(actionSource, /response\.status === 429/);
    assert.match(actionSource, /Retry-After/i);
    assert.match(actionSource, /status:\s*'rate_limited'/);
    assert.match(actionSource, /response\.status === 503/);
    assert.match(actionSource, /status:\s*'unavailable'/);
    assert.match(actionSource, /parsedReason\(payload\)/);
    assert.match(actionSource, /LIMIT_REASONS/);
    assert.match(actionSource, /remaining_free_questions/);
    assert.match(actionSource, /X-Omi-User-Id-Token/);
  });

  it('owns the Cloud Run ingress, identity, and frontend-only HMAC deployment contract', () => {
    const frontend = publicBuildContract.targets.frontend;
    const flags = frontend.deployment.flags;
    const prodFlags = Array.isArray(flags) ? flags : flags.prod || [];
    const developmentFlags = Array.isArray(flags) ? flags : flags.development || [];
    assert.ok(prodFlags.includes('--ingress=internal-and-cloud-load-balancing'));
    assert.equal(
      developmentFlags.includes('--ingress=internal-and-cloud-load-balancing'),
      false,
    );
    assert.equal(
      frontend.deployment.runtime_secrets.PUBLIC_SHARED_CONVERSATION_CHAT_IP_HMAC_KEY,
      'PUBLIC_SHARED_CONVERSATION_CHAT_IP_HMAC_KEY:latest',
    );
    assert.equal(frontend.deployment.runtime_secrets.OPENAI_API_KEY, undefined);
    assert.ok(frontend.deployment.remove_runtime_env_vars.includes('OPENAI_API_KEY'));
    assert.equal(frontend.deployment.runtime_secrets.DD_API_KEY, 'DD_API_KEY:latest');
    assert.match(deployActionSource, /service_account/);
    assert.match(deployActionSource, /runtime_env_vars/);
    assert.match(
      frontendWorkflowSource,
      /PUBLIC_SHARED_CONVERSATION_CHAT_FRONTEND_INVOKER_SA/,
    );
    assert.match(
      frontendWorkflowSource,
      /PUBLIC_SHARED_CONVERSATION_CHAT_FRONTEND_AUDIENCE/,
    );
    assert.doesNotMatch(
      frontendWorkflowSource,
      /test -n "\$PUBLIC_SHARED_CONVERSATION_CHAT_FRONTEND_INVOKER_SA"/,
    );
    assert.match(frontendWorkflowSource, /iam\\.gserviceaccount\\.com/);
  });

  it('passes only conversation id, bounded history, and the current question to the action', () => {
    assert.match(componentSource, /conversationId/);
    assert.match(componentSource, /history:\s*history\.slice\(-8\)/);
    assert.match(componentSource, /question:/);
    assert.doesNotMatch(componentSource, /chatWithMemory\(\{[^}]*transcript:/s);
  });

  it('offers the shared-chat limit options and emits integration events without PostHog', () => {
    assert.match(componentSource, /Sign in with Omi to keep asking/);
    assert.match(componentSource, /getOmiInstallLink\(userAgent\)/);
    assert.match(componentSource, /pages\/download\?/);
    assert.match(componentSource, /products\/omi\?/);
    assert.match(componentSource, /withCampaign\(APP_STORE\)/);
    assert.match(componentSource, /withCampaign\(PLAY_STORE\)/);
    assert.match(componentSource, /utm_source=omi_share/);
    assert.match(componentSource, /question_asked/);
    assert.match(componentSource, /limit_card_shown/);
    assert.match(componentSource, /upsell_clicked/);
    assert.doesNotMatch(componentSource, /posthog/i);
  });
});
