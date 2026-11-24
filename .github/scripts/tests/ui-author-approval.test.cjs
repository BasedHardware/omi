const {test} = require('node:test');
const assert = require('node:assert/strict');
const {readFileSync} = require('node:fs');
const {join} = require('node:path');
const {decision} = require('../ui-author-approval.cjs');
const actor = {id:9387252};
const nik = {id:43514161};
const pr = {user:{id:1},head:{sha:'a'.repeat(40)},commits:1,changed_files:1};
const ui = [{filename:'app/lib/pages/home.dart'}];
const approve = {id:1,user:nik,body:`/approve-ui ${pr.head.sha}`};
test('opener, author, committer and coauthor are gated', () => {
  assert.equal(decision({...pr,user:actor},ui,[],[]).allowed,false);
  for (const commit of [{author:actor},{committer:actor},{authors:[actor]}]) {
    assert.equal(decision(pr,ui,[commit],[]).allowed,false);
    assert.equal(decision(pr,ui,[commit],[approve]).allowed,true);
  }
});
test('other accounts and non-UI work pass; renamed UI is gated', () => {
  assert.equal(decision(pr,ui,[],[]).allowed,true);
  for (const filename of ['backend/router.py','app/lib/providers/home.dart','app/lib/backend/http/api.dart']) {
    assert.equal(decision({...pr,user:actor},[{filename}],[],[]).allowed,true);
  }
  assert.equal(decision({...pr,user:actor},[{filename:'archive/file',previous_filename:ui[0].filename}],[],[]).allowed,false);
});
test('Nik and David can approve only the current head; third accounts are ignored', () => {
  const p = {...pr,user:actor};
  for (const user of [nik,actor]) {
    assert.equal(decision(p,ui,[],[{...approve,user}]).allowed,true);
    assert.equal(decision(p,ui,[],[{...approve,user,body:'/approve-ui '+ 'b'.repeat(40)}]).allowed,false);
  }
  assert.equal(decision(p,ui,[],[{...approve,user:{id:3}}]).allowed,false);
  assert.equal(decision(p,ui,[],[]).allowed,false);
});
test('newest head command wins across either approver regardless of API order', () => {
  const p = {...pr,user:actor};
  for (const user of [nik,actor]) {
    const earlier = {...approve,user:user === nik ? actor : nik};
    const reject = {...approve,id:2,user,body:`/reject-ui ${pr.head.sha}`};
    assert.equal(decision(p,ui,[],[reject,earlier]).allowed,false);
    assert.equal(decision(p,ui,[],[reject,{...earlier,id:3}]).allowed,true);
    assert.equal(decision(p,ui,[],[earlier,{...reject,user:{id:3}}]).allowed,true);
    assert.equal(decision(p,ui,[],[earlier,{...reject,body:'/reject-ui '+ 'b'.repeat(40)}]).allowed,true);
  }
});
test('API truncation fails closed even with approval', () => {
  assert.equal(decision({...pr,commits:250},ui,[],[approve]).allowed,false);
  assert.equal(decision({...pr,changed_files:3001},ui,[],[approve]).allowed,false);
});
const run = require('../ui-author-approval.cjs');
function fixture() {
  const p = {...pr,number:1,user:actor,state:'open',base:{ref:'main',sha:'c'.repeat(40)}};
  const prs = [p];
  const comments = {1:[]};
  const statuses = [];
  const calls = [];
  const refs = new Set();
  const github = {rest:{pulls:{get:async ({pull_number}) => ({data:prs.find(p => p.number === pull_number)}),list:'prs'},
    issues:{listComments:'comments',createComment:async ({issue_number,body}) => {
      comments[issue_number].push({id:10,user:{type:'Bot'},body});
    }},git:{
      createRef:async ({ref}) => {
        const key = ref.slice('refs/'.length);
        if (refs.has(key)) throw Object.assign(new Error('Reference already exists'),{status:422});
        refs.add(key);
      },
      getRef:async ({ref}) => {
        if (!refs.has(ref)) throw Object.assign(new Error('Reference not found'),{status:404});
      },
      deleteRef:async ({ref}) => assert.ok(refs.delete(ref)),
    },repos:{createCommitStatus:async s => statuses.push({...s,node_id:String(statuses.length + 1)}),compareCommitsWithBasehead:async args => {
      calls.push(args);return {data:{files:ui,commits:[{sha:'d'.repeat(40)}],total_commits:1}};
    }}},paginate:async (method,args) => method === 'prs' ? prs.map(p => ({...p})) : comments[args.issue_number],
    graphql:async (query,args) => ({repository:{object:{oid:args.oid,authors:{totalCount:0,nodes:[]}}}})};
  github.paginate.iterator = async function* (method,{ref}) {
    yield {data:statuses.filter(s => s.sha === ref).reverse()};
  };
  const context = {repo:{owner:'test',repo:'test'},sha:p.base.sha,payload:{pull_request:{number:1}}};
  return {p,prs,comments,statuses,calls,github,context,refs};
}
test('over 100 same-head requests coalesce on main and keep the latest decision', async () => {
  const workflow = readFileSync(join(__dirname,'../../workflows/ui-author-approval.yml'),'utf8');
  const [requestJob, workerJob] = workflow.split('\n  guard:\n');
  assert.doesNotMatch(requestJob,/^\s*concurrency:/m);
  assert.match(workerJob,/if: github\.event_name == 'workflow_dispatch' && github\.ref == 'refs\/heads\/main'/);
  assert.match(workerJob,/group: .*inputs\.head_sha/);
  assert.match(workerJob,/cancel-in-progress: false/);
  assert.doesNotMatch(workerJob,/^\s*queue:/m);

  const f = fixture();
  const {github, context} = f;
  let pending;
  let requests = 0;
  github.rest.actions = {createWorkflowDispatch:async request => {
    assert.equal(request.ref,'main');
    assert.equal(request.workflow_id,'ui-author-approval.yml');
    assert.deepEqual(request.inputs,{pull_number:'1',head_sha:f.p.head.sha});
    // Model the platform's single waiting slot for the main worker.
    pending = request.inputs;
    requests++;
  }};
  const evaluate = inputs => run.evaluateDispatch({github,context:{...context,payload:{inputs}}});
  const atDecision = Promise.withResolvers();
  const finish = Promise.withResolvers();
  const list = github.paginate;
  github.paginate = Object.assign(async (method,args) => {
    const result = await list(method,args);
    if (method === 'comments' && requests === 1) {
      atDecision.resolve();
      const snapshot = [...result];
      await finish.promise;
      return snapshot;
    }
    return result;
  },{iterator:list.iterator});
  f.comments[1].push(approve);
  await run.requestEvaluation(f);
  const running = evaluate(pending);
  pending = undefined;
  await atDecision.promise;

  const commentContext = {...context,payload:{issue:{number:1,pull_request:{}}}};
  try {
    for (let i = 0; i < 101; i++) await run.requestEvaluation({github,context:commentContext});
    f.comments[1].push({id:2,user:nik,body:`/reject-ui ${f.p.head.sha}`});
    await run.requestEvaluation({github,context:commentContext});
    assert.equal(requests,103);
    assert.ok(f.statuses.every(s => s.state === 'pending'));
  } finally {
    finish.resolve();
    await running;
  }
  await evaluate(pending);
  assert.deepEqual(f.statuses.filter(s => s.state !== 'pending').map(({state,sha}) => [state,sha]),[
    ['failure',f.p.head.sha],
  ]);
});
test('a dispatch rejection replaces a same-head approval and cannot be evaluated by an old dispatch', async () => {
  const f = fixture();
  const {github,context,statuses,refs} = f;
  let inputs;
  github.rest.actions = {createWorkflowDispatch:async request => {inputs = request.inputs;}};
  f.comments[1].push(approve);
  await run.requestEvaluation(f);
  const evaluate = () => run.evaluateDispatch({github,context:{...context,payload:{inputs}}});
  await evaluate();
  assert.equal(statuses.at(-1).state,'success');
  github.rest.actions.createWorkflowDispatch = async () => {
    assert.equal(statuses.at(-1).state,'pending');
    throw new Error('rate limited');
  };
  await assert.rejects(run.requestEvaluation(f),/Could not request UI approval evaluation.*rate limited/);
  await evaluate();
  assert.deepEqual(statuses.map(s => s.state),['pending','pending','success','pending','failure']);
  assert.equal(refs.size,0);
});
test('request admission waits for a success write already in flight', async () => {
  const f = fixture();
  const {github,context,statuses} = f;
  let inputs;
  github.rest.actions = {createWorkflowDispatch:async request => {inputs = request.inputs;}};
  f.comments[1].push(approve);
  await run.requestEvaluation(f);
  const writing = Promise.withResolvers();
  const requested = Promise.withResolvers();
  const finish = Promise.withResolvers();
  const save = github.rest.repos.createCommitStatus;
  github.rest.repos.createCommitStatus = async status => {
    if (status.state === 'success') {
      writing.resolve();
      await finish.promise;
    }
    await save(status);
  };
  const getRef = github.rest.git.getRef;
  github.rest.git.getRef = async args => {
    await getRef(args);
    requested.resolve();
  };
  const running = run.evaluateDispatch({github,context:{...context,payload:{inputs}}});
  await writing.promise;
  const request = run.requestEvaluation(f);
  try {
    await requested.promise;
    assert.deepEqual(statuses.map(s => s.state),['pending','pending']);
  } finally {
    finish.resolve();
    await Promise.all([running,request]);
  }
  assert.deepEqual(statuses.map(s => s.state),['pending','pending','success','pending','pending']);
});
test('the dispatched worker rejects invalid routing inputs before writing status', async () => {
  const {github, context, statuses} = fixture();
  const dispatch = inputs => run.evaluateDispatch({github,context:{repo:context.repo,payload:{inputs}}});
  await assert.rejects(dispatch({pull_number:'1',head_sha:'main'}),/Invalid UI approval evaluation inputs/);
  await assert.rejects(dispatch({pull_number:'0',head_sha:pr.head.sha}),/Invalid UI approval evaluation inputs/);
  assert.deepEqual(statuses,[]);
});
test('workflow blocks repeatedly, notifies once per head, approves and revokes', async () => {
  const f = fixture();
  await run(f); await run(f); await run(f);
  assert.equal(f.comments[1].length,1);
  assert.ok(f.comments[1][0].body.includes('@kodjima33'));
  assert.equal(f.statuses.at(-1).state,'failure');
  f.comments[1].push(approve); await run(f);
  assert.equal(f.statuses.at(-1).state,'success');
  f.comments[1].pop(); await run(f);
  assert.equal(f.statuses.at(-1).state,'failure');
  f.p.head = {sha:'b'.repeat(40)};
  f.comments[1].push(approve); await run(f);
  assert.equal(f.statuses.at(-1).state,'failure');
  assert.equal(f.comments[1].filter(c => c.user.type === 'Bot').length,2);
  f.github.graphql = async () => {throw new Error('API failure');};
  await assert.rejects(run(f),/API failure/);
  assert.equal(f.statuses.at(-1).state,'failure');
});
test('another opener sharing SHA cannot clear the actor PR requirement', async () => {
  const f = fixture();
  f.prs.push({...f.p,number:2,user:{id:2}}); f.comments[2]=[];
  f.context.payload.pull_request.number=2;
  await run(f); assert.equal(f.statuses.at(-1).state,'failure');
  f.comments[1].push(approve);
  await run(f); assert.equal(f.statuses.at(-1).state,'success');
});
test('all evidence is immutable across H -> B -> H movement', async () => {
  const f = fixture();
  f.github.rest.pulls.listFiles = () => {throw new Error('mutable files forbidden');};
  f.github.rest.pulls.listCommits = () => {throw new Error('mutable commits forbidden');};
  await run(f);
  assert.equal(f.calls[0].basehead,`${f.p.base.sha}...${f.p.head.sha}`);
  f.github.rest.repos.compareCommitsWithBasehead = async () => ({data:{files:Array(300).fill(ui[0]),commits:[],total_commits:0}});
  await assert.rejects(run(f),/Incomplete immutable file/);
  assert.equal(f.statuses.at(-1).state,'failure');
});
test('actual desktop view locations are gated, services stay out', () => {
  for (const filename of ['desktop/windows/src/renderer/src/insightToast.tsx',
    'desktop/macos/Desktop/Sources/FloatingControlBar/FloatingControlBarView.swift',
    'desktop/macos/Desktop/Sources/Onboarding/SecondBrain/SBOnboardingView.swift']) {
    assert.equal(decision({...pr,user:actor},[{filename}],[],[]).allowed,false,filename);
  }
  for (const filename of ['desktop/macos/Desktop/Sources/Services/TranscriptionService.swift',
    'desktop/windows/src/main/transcription.ts']) {
    assert.equal(decision({...pr,user:actor},[{filename}],[],[]).allowed,true,filename);
  }
});

test('resolved SHA mismatch cannot evaluate another concurrency group', async () => {
  const f = fixture(); await run({...f,headSha:'e'.repeat(40)});
  assert.ok(f.statuses.every(s => s.sha === 'e'.repeat(40)));
  assert.equal(f.statuses.at(-1).state,'failure');
});
test('arbitrarily named SwiftUI file is gated by immutable contents', async () => {
  const f = fixture();
  f.github.rest.repos.compareCommitsWithBasehead = async () => ({data:{files:[{filename:'desktop/macos/Desktop/Sources/IntegrationNudges/IntegrationNudgeCard.swift'}],commits:[],total_commits:0}});
  const refs = [];
  f.github.rest.repos.getContent = async ({ref}) => {refs.push(ref);return {data:{encoding:'base64',size:Buffer.byteLength('import SwiftUI\nstruct IntegrationNudgeCard: View {}'),content:Buffer.from('import SwiftUI\nstruct IntegrationNudgeCard: View {}').toString('base64')}};};
  await run(f);
  assert.equal(f.statuses.at(-1).state,'failure');
  assert.deepEqual(refs,[f.p.base.sha,f.p.head.sha]);
  f.github.rest.repos.getContent = async () => ({data:{encoding:'base64',size:Buffer.byteLength('import Foundation\nclass Service {}'),content:Buffer.from('import Foundation\nclass Service {}').toString('base64')}});
  await run(f); assert.equal(f.statuses.at(-1).state,'success');
});

test('arbitrarily named AppKit panel requires approval', async () => {
  const f = fixture();
  f.github.rest.repos.compareCommitsWithBasehead = async () => ({data:{files:[{filename:'desktop/macos/Desktop/Sources/Chrome/CustomChrome.swift'}],commits:[],total_commits:0}});
  f.github.rest.repos.getContent = async () => ({data:{encoding:'base64',size:Buffer.byteLength('import AppKit; class CustomChrome: NSPanel {}'),content:Buffer.from('import AppKit; class CustomChrome: NSPanel {}').toString('base64')}});
  await run(f); assert.equal(f.statuses.at(-1).state,'failure');
});

test('moved trigger still reconciles revoked approval on remaining locked-head PR', async () => {
  const f = fixture(); const locked = f.p.head.sha;
  f.prs.push({...f.p,number:2,head:{sha:'e'.repeat(40)},user:{id:2}});
  f.context.payload.pull_request.number=2; f.comments[2]=[];
  await run({...f,headSha:locked});
  assert.equal(f.statuses.at(-1).state,'failure');
  assert.ok(f.statuses.every(s => s.sha === locked));
});

function largeSwiftFixture(source, filename = 'desktop/macos/Desktop/Sources/Services/Large.generated.swift') {
  const f = fixture();
  f.github.rest.repos.compareCommitsWithBasehead = async () => ({data:{files:[{filename}],commits:[],total_commits:0}});
  const body = source + ' '.repeat(1128966 - Buffer.byteLength(source));
  const sha = require('node:crypto').createHash('sha1').update(`blob ${Buffer.byteLength(body)}\0${body}`).digest('hex');
  const metadata = {encoding:'none',content:'',size:Buffer.byteLength(body),sha};
  const refs = [], blobs = [];
  f.github.rest.repos.getContent = async ({ref,path}) => {
    refs.push(ref); assert.equal(path,filename); return {data:{...metadata}};
  };
  f.github.rest.git = {getBlob:async ({file_sha}) => {
    blobs.push(file_sha);
    return {data:{...metadata,encoding:'base64',content:Buffer.from(body).toString('base64')}};
  }};
  return {...f,metadata,refs,blobs};
}
test('other large generated Swift is scanned at both immutable refs without a waiver', async () => {
  const f = largeSwiftFixture('import Foundation\n');
  await run(f);
  assert.equal(f.statuses.at(-1).state,'success');
  assert.deepEqual(f.refs,[f.p.base.sha,f.p.head.sha]);
  assert.deepEqual(f.blobs,[f.metadata.sha,f.metadata.sha]);
  const ui = largeSwiftFixture('import SwiftUI\n');
  await run(ui);
  assert.equal(ui.statuses.at(-1).state,'failure');
  ui.comments[1].push(approve); await run(ui);
  assert.equal(ui.statuses.at(-1).state,'success');
});
test('large Swift rejects absent, oversized, mismatched and truncated blob evidence', async () => {
  for (const mutation of ['sha','size','encoding','content','404','500','oversize','missing-sha']) {
    const f = largeSwiftFixture('import Foundation\n');
    const getBlob = f.github.rest.git.getBlob;
    f.github.rest.git.getBlob = async args => {
      if (mutation === '404' || mutation === '500') throw Object.assign(new Error('blob unavailable'),{status:Number(mutation)});
      const result = await getBlob(args);
      result.data[mutation] = mutation === 'size' ? 1 : 'invalid';
      return result;
    };
    if (mutation === 'oversize') f.metadata.size = 10000001;
    if (mutation === 'missing-sha') delete f.metadata.sha;
    await assert.rejects(run(f));
    assert.equal(f.statuses.at(-1).state,'failure',mutation);
  }
});

const generatedApiFiles = [
  'desktop/windows/src/renderer/src/lib/omiApi.generated.ts',
  'web/app/src/lib/omiApi.generated.ts',
  'web/admin/lib/services/omi-api/omiApi.generated.ts',
  'web/personas-open-source/src/lib/omiApi.generated.ts',
  'desktop/macos/Desktop/Sources/Generated/OmiApi.generated.swift',
];
test('generated API outputs alone pass without approval or Swift source fetches', async () => {
  const f = fixture();
  f.github.rest.repos.compareCommitsWithBasehead = async () => ({data:{
    files:generatedApiFiles.map(filename => ({filename})),commits:[],total_commits:0,
  }});
  f.github.rest.repos.getContent = async () => assert.fail('generated API source must not be fetched');
  await run(f);
  assert.equal(f.statuses.at(-1).state,'success');
  assert.equal(f.comments[1].length,0);
  const large = largeSwiftFixture('import SwiftUI\n',generatedApiFiles.at(-1));
  await run(large);
  assert.equal(large.statuses.at(-1).state,'success');
  assert.deepEqual(large.refs,[]);
  assert.deepEqual(large.blobs,[]);
});
test('generated API outputs do not exempt real UI, other generated UI, or renamed UI', () => {
  const p = {...pr,user:actor};
  const files = generatedApiFiles.map(filename => ({filename}));
  for (const filename of [
    'web/app/src/features/settings/Settings.tsx',
    'web/personas-open-source/src/components/Profile.generated.tsx',
    'desktop/macos/Desktop/Sources/Views/Other.generated.swift',
  ]) {
    assert.equal(decision(p,[...files,{filename}],[],[]).required,true,filename);
    assert.equal(decision(p,[...files,{filename}],[],[]).allowed,false,filename);
  }
  assert.equal(decision(p,[{filename:generatedApiFiles[0],previous_filename:ui[0].filename}],[],[]).required,true);
});
test('renames to or from the exempt Swift output still inspect the other Swift path', async () => {
  for (const reverse of [false,true]) {
    const f = fixture();
    const paths = [generatedApiFiles.at(-1),'desktop/macos/Desktop/Sources/Services/Custom.swift'];
    if (reverse) paths.reverse();
    f.github.rest.repos.compareCommitsWithBasehead = async () => ({data:{
      files:[{filename:paths[0],previous_filename:paths[1]}],commits:[],total_commits:0,
    }});
    const refs = [];
    f.github.rest.repos.getContent = async ({path,ref}) => {
      assert.equal(path,'desktop/macos/Desktop/Sources/Services/Custom.swift');
      refs.push(ref);
      const source = 'import SwiftUI';
      return {data:{encoding:'base64',size:Buffer.byteLength(source),content:Buffer.from(source).toString('base64')}};
    };
    await run(f);
    assert.equal(f.statuses.at(-1).state,'failure');
    assert.deepEqual(refs,[f.p.base.sha,f.p.head.sha]);
  }
});

const {carryCandidate} = require('../ui-author-approval.cjs');
const A = 'a'.repeat(40), B = 'b'.repeat(40), C = 'c'.repeat(40);
const cmd = (id, verb, sha, user = nik) => ({id, user, body:`/${verb}-ui ${sha}`});
test('R29 carry candidate: newest approver command must approve an earlier head', () => {
  assert.equal(carryCandidate([cmd(1,'approve',A)],B),A);
  assert.equal(carryCandidate([cmd(1,'approve',A,actor)],B),A);
  assert.equal(carryCandidate([cmd(2,'reject',C),cmd(1,'approve',A)],B),null);
  assert.equal(carryCandidate([cmd(1,'approve',A),cmd(2,'reject',B)],B),null);
  assert.equal(carryCandidate([cmd(1,'approve',A),cmd(2,'approve',B)],B),null);
  assert.equal(carryCandidate([cmd(1,'approve',A,{id:3})],B),null);
  assert.equal(carryCandidate([],B),null);
  assert.equal(carryCandidate([{id:1,user:nik,body:`/approve-ui ${A} please`}],B),null);
});
test('decision uses a carried approval only without a current-head command', () => {
  const p = {...pr,user:actor};
  assert.equal(decision(p,ui,[],[],true).allowed,true);
  assert.equal(decision(p,ui,[],[{...approve,body:`/reject-ui ${pr.head.sha}`}],true).allowed,false);
  assert.equal(decision({...p,commits:250},ui,[],[],true).allowed,false);
});
function carryFixture({rangeFiles, status = 'ahead'}) {
  const f = fixture();
  const approved = f.p.head.sha;
  f.p.head = {sha:B};
  f.comments[1].push(cmd(1,'approve',approved));
  f.github.rest.repos.compareCommitsWithBasehead = async args => {
    f.calls.push(args);
    if (args.basehead === `${approved}...${B}`) {
      return {data:{files:rangeFiles,commits:[{sha:B}],total_commits:1,status}};
    }
    return {data:{files:ui,commits:[{sha:B}],total_commits:1}};
  };
  return {...f,approved};
}
test('R29 workflow carries approval across a descendant head with no UI change', async () => {
  const f = carryFixture({rangeFiles:[{filename:'backend/router.py'}]});
  await run(f);
  assert.equal(f.statuses.at(-1).state,'success');
  assert.ok(f.calls.some(c => c.basehead === `${f.approved}...${B}`));
  assert.equal(f.comments[1].filter(c => c.user.type === 'Bot').length,0);
});
test('R29 carry refuses UI changes, rebases, unreadable ranges and later rejects', async () => {
  for (const [label, opts] of [
    ['ui', {rangeFiles:[{filename:'app/lib/pages/home.dart'}]}],
    ['renamed-ui', {rangeFiles:[{filename:'archive/x',previous_filename:'app/lib/widgets/x.dart'}]}],
    ['rebase', {rangeFiles:[{filename:'backend/router.py'}],status:'diverged'}],
    ['behind', {rangeFiles:[],status:'behind'}],
    ['truncated', {rangeFiles:Array(300).fill({filename:'backend/router.py'})}],
  ]) {
    const f = carryFixture(opts);
    await run(f);
    assert.equal(f.statuses.at(-1).state,'failure',label);
  }
  const f = carryFixture({rangeFiles:[{filename:'backend/router.py'}]});
  f.comments[1].push(cmd(2,'reject',f.approved));
  await run(f);
  assert.equal(f.statuses.at(-1).state,'failure');
});
test('R29 carry scans Swift in the range by content', async () => {
  const f = carryFixture({rangeFiles:[{filename:'desktop/macos/Desktop/Sources/Chrome/Custom.swift'}]});
  const source = 'import SwiftUI';
  f.github.rest.repos.getContent = async () => ({data:{encoding:'base64',size:Buffer.byteLength(source),content:Buffer.from(source).toString('base64')}});
  await run(f);
  assert.equal(f.statuses.at(-1).state,'failure');
});
