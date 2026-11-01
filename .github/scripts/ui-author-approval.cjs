// Account-scoped UI approval. All inputs are API data, never executable PR code.
const ACTOR_ID = 9387252; // Git-on-my-level, stable across login renames.
const NIK_ID = 43514161;
const STATUS = 'UI author approval';
const MARKER = '<!-- ui-author-approval:git-on-my-level -->';
const isActor = user => user?.id === ACTOR_ID;
const isUI = path => /^(app\/lib\/(pages|widgets|ui|l10n)\/|desktop\/macos\/Desktop\/(Sources\/(Views|Components|Theme|UI)\/|Resources\/)|desktop\/windows\/src\/(components|pages|views|styles)\/|web\/[^/]+\/(app|src)\/.*\.(tsx|jsx|vue|css|scss|html|svg|png|jpg|webp)$|frontend\/.*\.(tsx|jsx|vue|css|scss|html|svg|png|jpg|webp)$)/.test(path)
  || /^desktop\/macos\/Desktop\/Sources\/.*(View|ViewController|Window|Panel)\.swift$/.test(path)
  || /^desktop\/windows\/src\/renderer\/.*\.(tsx|jsx|css|scss|html|svg|png|jpg|webp)$/.test(path)
  || /\.(figma|sketch)$/.test(path);

function decision(pr, files, commits, comments) {
  const actor = isActor(pr.user) || commits.some(c => isActor(c.author) || isActor(c.committer)
    || (c.authors || []).some(isActor));
  const ui = files.some(f => f.ui || isUI(f.filename) || (f.previous_filename && isUI(f.previous_filename)));
  // REST caps PR commits at 250 and files at 3000. Never pass incomplete evidence.
  const incomplete = pr.commits >= 250 || pr.changed_files > 3000;
  const required = incomplete || (actor && ui);
  const commands = comments.filter(c => c.user?.id === NIK_ID
    && new RegExp(`^/(approve|reject)-ui ${pr.head.sha}\\s*$`).test(c.body.trim()));
  commands.sort((a, b) => a.id - b.id);
  const approved = commands.at(-1)?.body.trim().startsWith('/approve-ui ');
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
      if (!/^desktop\/macos\/.*\.swift$/.test(path)) continue;
      for (const ref of [pr.base.sha,pr.head.sha]) {
        try {
          const {data} = await github.rest.repos.getContent({...repo,path,ref});
          if (data.encoding !== 'base64' || !data.content || data.size > 1000000) {
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
  return {files:first.files,commits};
}

async function evaluateHead({github, context, headSha}) {
  const repo = context.repo;
  const pull_number = context.payload.pull_request?.number || context.payload.issue.number;
  const trigger = (await github.rest.pulls.get({...repo,pull_number})).data;
  if (!headSha && (trigger.state !== 'open' || trigger.base.ref !== 'main')) return;
  const sha = headSha || trigger.head.sha;
  const status = (state, description) => github.rest.repos.createCommitStatus({
    ...repo,sha,state,context:STATUS,description,
  });
  await status('pending','Checking account-scoped UI approval');
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
      const result = decision(pr,files,commits,comments);
      allowed &&= result.allowed;
      const marker = `${MARKER.slice(0,-4)}:${sha} -->`;
      if (result.required && !comments.some(c => c.user?.type === 'Bot' && c.body.includes(marker))) {
        await github.rest.issues.createComment({...repo,issue_number:pr.number,body:
          `${marker}\n@kodjima33 UI changes involving Git-on-my-level require your approval. `
          + `Review the current diff, then comment \`/approve-ui ${sha}\`. `
          + 'Each new head needs a fresh approval. To withdraw it, comment `/reject-ui <full head SHA>`. '
          + 'Non-UI work and unrelated access are unaffected.'});
      }
    }
    const latest = await sameHead();
    const signature = list => list.map(p => `${p.number}:${p.base.sha}`).sort().join(',');
    if (signature(latest) !== signature(prs)) throw new Error('PR set changed during verification');
    await status(allowed ? 'success' : 'failure',allowed
      ? 'UI approval satisfied or not required on all same-head PRs'
      : 'Waiting for kodjima33 approval on affected same-head PRs');
  } catch (error) {
    await status('failure','Unable to verify UI approval; see workflow logs');
    throw error;
  }
}
async function run(args) {
  // Workflow concurrency is keyed to the resolved immutable head. Replaced
  // pending events therefore still evaluate that same head's latest comments.
  return evaluateHead(args);
}
module.exports = run;
module.exports.decision = decision;
module.exports.evidence = evidence;
