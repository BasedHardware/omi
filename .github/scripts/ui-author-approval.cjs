// Account-scoped UI approval. All inputs are API data, never executable PR code.
const ACTOR_ID = 9387252; // Git-on-my-level, stable across login renames.
const NIK_ID = 43514161;
const STATUS = 'UI author approval';
const MARKER = '<!-- ui-author-approval:git-on-my-level -->';
const isActor = user => user?.id === ACTOR_ID;
const isUI = path => /^(app\/lib\/(pages|widgets|ui|l10n)\/|desktop\/macos\/Desktop\/(Sources\/(Views|Components|Theme|UI)\/|Resources\/)|desktop\/windows\/src\/(components|pages|views|styles)\/|web\/[^/]+\/(app|src)\/.*\.(tsx|jsx|vue|css|scss|html|svg|png|jpg|webp)$|frontend\/.*\.(tsx|jsx|vue|css|scss|html|svg|png|jpg|webp)$)/.test(path)
  || /\.(figma|sketch)$/.test(path);

function decision(pr, files, commits, comments) {
  const actor = isActor(pr.user) || commits.some(c => isActor(c.author) || isActor(c.committer)
    || (c.authors || []).some(isActor));
  const ui = files.some(f => isUI(f.filename) || (f.previous_filename && isUI(f.previous_filename)));
  // REST caps PR commits at 250 and files at 3000. Never pass incomplete evidence.
  const incomplete = pr.commits >= 250 || pr.changed_files > 3000;
  const required = incomplete || (actor && ui);
  const commands = comments.filter(c => c.user?.id === NIK_ID
    && new RegExp(`^/(approve|reject)-ui ${pr.head.sha}\\s*$`).test(c.body.trim()));
  commands.sort((a, b) => a.id - b.id);
  const approved = commands.at(-1)?.body.trim().startsWith('/approve-ui ');
  return {required, allowed: !required || (!incomplete && !!approved), incomplete};
}

async function run({github, context}) {
  const repo = context.repo;
  const pull_number = context.payload.pull_request?.number || context.payload.issue.number;
  const pr = (await github.rest.pulls.get({...repo, pull_number})).data;
  if (pr.state !== 'open' || pr.base.ref !== 'main') return;
  const sha = pr.head.sha;
  const marker = `${MARKER.slice(0, -4)}:${sha} -->`;
  const status = (state, description) => github.rest.repos.createCommitStatus({
    ...repo, sha, state, context: STATUS, description,
  });
  await status('pending', 'Checking account-scoped UI approval');
  try {
    const [files, commits, comments] = await Promise.all([
      github.paginate(github.rest.pulls.listFiles, {...repo, pull_number, per_page: 100}),
      github.paginate(github.rest.pulls.listCommits, {...repo, pull_number, per_page: 100}),
      github.paginate(github.rest.issues.listComments, {...repo, issue_number: pull_number, per_page: 100}),
    ]);
    // REST exposes primary authors only. GraphQL includes GitHub-linked coauthors.
    const authors = [];
    let cursor = null;
    do {
      const data = await github.graphql(`query($owner:String!,$name:String!,$number:Int!,$cursor:String) {
        repository(owner:$owner,name:$name) { pullRequest(number:$number) {
          commits(first:100,after:$cursor) { pageInfo { hasNextPage endCursor }
            nodes { commit { authors(first:100) { totalCount nodes { user { databaseId } } } } }
          }
        } }
      }`, {owner:repo.owner, name:repo.repo, number:pull_number, cursor});
      const page = data.repository.pullRequest.commits;
      for (const node of page.nodes) {
        if (node.commit.authors.totalCount > 100) throw new Error('Incomplete coauthor evidence');
        authors.push({authors:node.commit.authors.nodes.map(a => ({id:a.user?.databaseId}))});
      }
      cursor = page.pageInfo.hasNextPage ? page.pageInfo.endCursor : null;
    } while (cursor);
    const result = decision(pr, files, [...commits, ...authors], comments);
    if (result.required && !comments.some(c => c.user?.type === 'Bot' && c.body.includes(marker))) {
      await github.rest.issues.createComment({...repo, issue_number:pull_number, body:
        `${marker}\n@kodjima33 UI changes involving Git-on-my-level require your approval. `
        + `Review the current diff, then comment \`/approve-ui ${sha}\`. `
        + 'Each new head needs a fresh approval. To withdraw it, comment `/reject-ui <full head SHA>`. '
        + 'Non-UI work and unrelated access are unaffected.'});
    }
    const latest = (await github.rest.pulls.get({...repo, pull_number})).data;
    if (latest.head.sha !== sha) return; // The synchronize run evaluates the new head.
    await status(result.allowed ? 'success' : 'failure', result.incomplete
      ? 'Incomplete PR evidence; split the PR before approval'
      : result.allowed ? 'UI approval satisfied or not required' : 'Waiting for kodjima33 approval of this head');
  } catch (error) {
    await status('failure', 'Unable to verify UI approval; see workflow logs');
    throw error;
  }
}
module.exports = run;
module.exports.decision = decision;
