// Account-scoped UI approval. All inputs are API data, never executable PR code.
const {setTimeout: delay} = require('node:timers/promises');
const ACTOR_ID = 9387252; // Git-on-my-level, stable across login renames.
const NIK_ID = 43514161;
const APPROVER_IDS = new Set([NIK_ID, ACTOR_ID]);
// Exact default outputs of backend/scripts/generate_{ts,swift}_openapi_types.py.
// Keep this bounded: other generated files can still contain UI.
const GENERATED_API_FILES = new Set([
  'desktop/windows/src/renderer/src/lib/omiApi.generated.ts',
  'web/app/src/lib/omiApi.generated.ts',
  'web/admin/lib/services/omi-api/omiApi.generated.ts',
  'web/personas-open-source/src/lib/omiApi.generated.ts',
  'desktop/macos/Desktop/Sources/Generated/OmiApi.generated.swift',
]);
const STATUS = 'UI author approval';
const READY = 'Checking account-scoped UI approval';
const MARKER = '<!-- ui-author-approval:git-on-my-level -->';
const isActor = user => user?.id === ACTOR_ID;
const isUI = path => !GENERATED_API_FILES.has(path) && (/^(app\/lib\/(pages|widgets|ui|l10n)\/|desktop\/macos\/Desktop\/(Sources\/(Views|Components|Theme|UI)\/|Resources\/)|desktop\/windows\/src\/(components|pages|views|styles)\/|web\/[^/]+\/(app|src)\/.*\.(tsx|jsx|vue|css|scss|html|svg|png|jpg|webp)$|frontend\/.*\.(tsx|jsx|vue|css|scss|html|svg|png|jpg|webp)$)/.test(path)
  || /^desktop\/macos\/Desktop\/Sources\/.*(View|ViewController|Window|Panel)\.swift$/.test(path)
  || /^desktop\/windows\/src\/renderer\/.*\.(tsx|jsx|css|scss|html|svg|png|jpg|webp)$/.test(path)
  || /\.(figma|sketch)$/.test(path));

const touchesUI = files => files.some(f => f.ui || isUI(f.filename)
  || (f.previous_filename && isUI(f.previous_filename)));
const COMMAND = /^\/(approve|reject)-ui ([a-f0-9]{40})\s*$/;
const approverCommands = comments => comments
  .filter(c => APPROVER_IDS.has(c.user?.id) && COMMAND.test(c.body.trim()))
  .sort((a, b) => a.id - b.id);

// R29 (David, 2026-11-20): an approval carries to a later head only when the
// newest approver command on the PR is an /approve-ui for an earlier head (any
// later /reject-ui withdraws it) and nothing was said about the current head.
// The caller must still prove the UI did not change between the two heads.
function carryCandidate(comments, headSha) {
  const commands = approverCommands(comments);
  if (commands.some(c => c.body.trim().match(COMMAND)[2] === headSha)) return null;
  const [, verb, sha] = commands.at(-1)?.body.trim().match(COMMAND) || [];
  return verb === 'approve' ? sha : null;
}

function decision(pr, files, commits, comments, carried = false) {
  const actor = isActor(pr.user) || commits.some(c => isActor(c.author) || isActor(c.committer)
    || (c.authors || []).some(isActor));
  const ui = touchesUI(files);
  // REST caps PR commits at 250 and files at 3000. Never pass incomplete evidence.
  const incomplete = pr.commits >= 250 || pr.changed_files > 3000;
  const required = incomplete || (actor && ui);
  const commands = comments.filter(c => APPROVER_IDS.has(c.user?.id)
    && new RegExp(`^/(approve|reject)-ui ${pr.head.sha}\\s*$`).test(c.body.trim()));
  commands.sort((a, b) => a.id - b.id);
  const approved = commands.length ? commands.at(-1).body.trim().startsWith('/approve-ui ') : carried;
  return {required, allowed: !required || (!incomplete && !!approved), incomplete};
}

async function evidence(github, repo, pr) {
  const basehead = `${pr.base.sha}...${pr.head.sha}`;
  const first = (await github.rest.repos.compareCommitsWithBasehead({
    ...repo, basehead, per_page:100, page:1,
  })).data;
  // Compare files are capped at 300, even with commit pagination. Fail closed
  // at the boundary rather than treating a truncated snapshot as non-UI.
  if (!first.files || first.files.length >= 300) throw new Error('Incomplete immutable file evidence');
  const commits = [...first.commits];
  for (let page = 2; commits.length < first.total_commits; page++) {
    const next = (await github.rest.repos.compareCommitsWithBasehead({
      ...repo, basehead, per_page:100, page,
    })).data;
    if (!next.commits.length || next.total_commits !== first.total_commits) {
      throw new Error('Incomplete immutable commit evidence');
    }
    commits.push(...next.commits);
  }
  if (commits.length !== first.total_commits) throw new Error('Incomplete commit evidence');
  for (const commit of commits) {
    const data = await github.graphql(`query($owner:String!,$name:String!,$oid:GitObjectID!) {
      repository(owner:$owner,name:$name) { object(oid:$oid) { ... on Commit {
        oid authors(first:100) { totalCount nodes { user { databaseId } } }
      } } }
    }`, {owner:repo.owner,name:repo.repo,oid:commit.sha});
    const object = data.repository.object;
    if (!object || object.oid !== commit.sha || object.authors.totalCount > 100
      || object.authors.nodes.length !== object.authors.totalCount) {
      throw new Error('Incomplete immutable coauthor evidence');
    }
    commit.authors = object.authors.nodes.map(a => ({id:a.user?.databaseId}));
  }
  // Inspect immutable Swift source as data, so UI declarations in arbitrarily
  // named files (for example IntegrationNudgeCard.swift) cannot evade the gate.
  for (const file of first.files) {
    for (const path of new Set([file.filename,file.previous_filename].filter(Boolean))) {
      if (GENERATED_API_FILES.has(path) || !/^desktop\/macos\/.*\.swift$/.test(path)) continue;
      for (const ref of [pr.base.sha,pr.head.sha]) {
        try {
          let {data} = await github.rest.repos.getContent({...repo,path,ref});
          // Contents omits the body above 1 MB. Read that exact immutable blob
          // for non-exempt Swift files on both sides of the diff.
          if (data.encoding === 'none' && data.size > 1000000 && data.size <= 10000000
            && /^[a-f0-9]{40}$/.test(data.sha)) {
            const metadata = data;
            try {
              ({data} = await github.rest.git.getBlob({...repo,file_sha:metadata.sha}));
            } catch (error) {
              // Only a missing path at getContent may be treated as a deletion.
              throw new Error('Incomplete Swift source evidence: blob fetch failed',{cause:error});
            }
            if (data.sha !== metadata.sha || data.size !== metadata.size) {
              throw new Error('Incomplete Swift source evidence');
            }
          }
          if (data.encoding !== 'base64' || !data.content || data.size > 10000000
            || Buffer.from(data.content,'base64').length !== data.size) {
            throw new Error('Incomplete Swift source evidence');
          }
          const source = Buffer.from(data.content,'base64').toString('utf8');
          file.ui ||= /\bimport\s+(?:SwiftUI|AppKit)\b|:\s*(?:[\w.]+\s*,\s*)*(?:NSView|NSViewController|NSPanel|NSWindow|UIView|UIViewController)\b/.test(source);
        } catch (error) {
          if (error.status !== 404) throw error;
        }
      }
    }
  }
  return {files:first.files,commits,status:first.status};
}

// The approved head must be an ancestor of the current head, so the compare is
// exactly approved..current; a rebase or force-push needs a fresh approval. Any
// UI file in that range, including Swift UI found by content, refuses the carry.
async function unchangedUI(github, repo, approvedSha, headSha) {
  try {
    const range = await evidence(github, repo, {base:{sha:approvedSha}, head:{sha:headSha}});
    return ['ahead','identical'].includes(range.status) && !touchesUI(range.files);
  } catch (error) {
    return false;
  }
}

const publishStatus = (github, repo, sha, state, description) => github.rest.repos.createCommitStatus({
  ...repo,sha,state,context:STATUS,description,
});

async function latestStatus(github, repo, sha) {
  const pages = github.paginate.iterator(github.rest.repos.listCommitStatusesForRef, {
    ...repo,ref:sha,per_page:100,
  });
  for await (const {data} of pages) {
    const latest = data.find(status => status.context.toLowerCase() === STATUS.toLowerCase());
    if (latest) return latest;
  }
}

// Status creation is append-only, with no compare-and-set. Serialize the
// read/write pair with request admission, without putting PR jobs in the
// worker's cancellable queue. GitHub creates a named ref at most once.
async function withStatusLock(github, context, sha, operation) {
  const ref = `tags/ui-author-approval-lock/${sha}`;
  const args = {...context.repo,ref};
  const deadline = Date.now() + 45_000;
  for (;;) {
    try {
      await github.rest.git.createRef({...args,ref:`refs/${ref}`,sha:context.sha});
      break;
    } catch (error) {
      if (![409,422].includes(error.status)) throw error;
      try {
        await github.rest.git.getRef(args);
      } catch (lookupError) {
        // A previous holder may have released between create and lookup.
        if (lookupError.status !== 404) throw lookupError;
      }
      if (Date.now() >= deadline) throw new Error(`Could not acquire UI approval status lock: ${ref}`,{cause:error});
      await delay(200 + Math.random() * 300);
    }
  }
  try {
    return await operation();
  } finally {
    await github.rest.git.deleteRef(args);
  }
}

async function evaluateHead({github, context, headSha, pullNumber, requestId}) {
  const repo = context.repo;
  const pull_number = pullNumber ?? (context.payload.pull_request?.number || context.payload.issue.number);
  const trigger = (await github.rest.pulls.get({...repo,pull_number})).data;
  if (!headSha && (trigger.state !== 'open' || trigger.base.ref !== 'main')) return;
  const sha = headSha || trigger.head.sha;
  const status = (state, description) => {
    if (!requestId) return publishStatus(github,repo,sha,state,description);
    return withStatusLock(github,context,sha,async () => {
      const latest = await latestStatus(github,repo,sha);
      if (latest?.node_id === requestId) await publishStatus(github,repo,sha,state,description);
    });
  };
  if (!requestId) await status('pending',READY);
  try {
    // Commit statuses are shared by SHA, so every open main PR sharing this
    // SHA must satisfy its own requirements before any run may write success.
    const sameHead = async () => (await github.paginate(github.rest.pulls.list, {
      ...repo,state:'open',base:'main',per_page:100,
    })).filter(p => p.head.sha === sha);
    const prs = await sameHead();
    let allowed = prs.length > 0;
    for (const summary of prs) {
      const pr = (await github.rest.pulls.get({...repo,pull_number:summary.number})).data;
      if (pr.head.sha !== sha || pr.base.ref !== 'main') throw new Error('PR snapshot changed');
      const {files,commits} = await evidence(github,repo,pr);
      const comments = await github.paginate(github.rest.issues.listComments, {
        ...repo,issue_number:pr.number,per_page:100,
      });
      let result = decision(pr,files,commits,comments);
      const candidate = result.allowed || result.incomplete ? null : carryCandidate(comments,sha);
      if (candidate && await unchangedUI(github,repo,candidate,sha)) {
        result = decision(pr,files,commits,comments,true);
      }
      allowed &&= result.allowed;
      const marker = `${MARKER.slice(0,-4)}:${sha} -->`;
      if (result.required && !result.allowed
        && !comments.some(c => c.user?.type === 'Bot' && c.body.includes(marker))) {
        await github.rest.issues.createComment({...repo,issue_number:pr.number,body:
          `${marker}\n@kodjima33 UI changes involving Git-on-my-level require your approval. `
          + `Review the current diff, then comment \`/approve-ui ${sha}\`. `
          + 'A later head keeps the approval only when it adds commits on top with no UI changes; '
          + 'a UI change, rebase or force-push needs a fresh one. To withdraw it, comment `/reject-ui <full head SHA>`. '
          + 'Non-UI work and unrelated access are unaffected.'});
      }
    }
    const latest = await sameHead();
    const signature = list => list.map(p => `${p.number}:${p.base.sha}`).sort().join(',');
    if (signature(latest) !== signature(prs)) throw new Error('PR set changed during verification');
    await status(allowed ? 'success' : 'failure',allowed
      ? 'UI approval satisfied or not required on all same-head PRs'
      : 'Waiting for Nik or David approval on affected same-head PRs');
  } catch (error) {
    await status('failure','Unable to verify UI approval; see workflow logs');
    throw error;
  }
}
async function requestEvaluation({github, context}) {
  const pull_number = context.payload.pull_request?.number || context.payload.issue.number;
  const {data: pr} = await github.rest.pulls.get({...context.repo,pull_number});
  const sha = pr.head.sha;
  if (!/^[a-f0-9]{40}$/.test(sha)) throw new Error('Invalid head SHA');
  return withStatusLock(github,context,sha,async () => {
    await publishStatus(github,context.repo,sha,'pending','Requesting UI approval evaluation');
    try {
      await github.rest.actions.createWorkflowDispatch({
        ...context.repo,
        workflow_id:'ui-author-approval.yml',
        ref:'main',
        inputs:{pull_number:String(pull_number),head_sha:sha},
      });
    } catch (error) {
      await publishStatus(github,context.repo,sha,'failure','Could not dispatch UI approval evaluation; see workflow logs');
      throw new Error(`Could not request UI approval evaluation for ${sha}: ${error.message}`,{cause:error});
    }
    // Dispatch arrival is unordered. Any surviving worker may evaluate the
    // latest successfully dispatched request, after capturing its status ID.
    await publishStatus(github,context.repo,sha,'pending',READY);
  });
}

async function evaluateDispatch({github, context}) {
  const {pull_number, head_sha: headSha} = context.payload.inputs;
  const pullNumber = Number(pull_number);
  if (!/^[1-9][0-9]*$/.test(pull_number) || !Number.isSafeInteger(pullNumber)
      || !/^[a-f0-9]{40}$/.test(headSha)) {
    throw new Error('Invalid UI approval evaluation inputs');
  }
  const latest = await withStatusLock(github,context,headSha,() => latestStatus(github,context.repo,headSha));
  if (latest?.state !== 'pending' || latest.description !== READY || !latest.node_id) return;
  return evaluateHead({github,context,headSha,pullNumber,requestId:latest.node_id});
}

module.exports = evaluateHead;
module.exports.requestEvaluation = requestEvaluation;
module.exports.evaluateDispatch = evaluateDispatch;
module.exports.decision = decision;
module.exports.evidence = evidence;
module.exports.carryCandidate = carryCandidate;
