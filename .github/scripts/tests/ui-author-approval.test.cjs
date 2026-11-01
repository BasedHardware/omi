const {test} = require('node:test');
const assert = require('node:assert/strict');
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
test('only Nik current-head explicit approval passes; revocation wins', () => {
  const p = {...pr,user:actor};
  for (const comment of [{...approve,user:actor},{...approve,body:'/approve-ui '+ 'b'.repeat(40)}]) {
    assert.equal(decision(p,ui,[],[comment]).allowed,false);
  }
  assert.equal(decision(p,ui,[],[approve,{...approve,id:2,body:`/reject-ui ${pr.head.sha}`}]).allowed,false);
  assert.equal(decision(p,ui,[],[]).allowed,false);
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
  const github = {rest:{pulls:{get:async ({pull_number}) => ({data:prs.find(p => p.number === pull_number)}),list:'prs'},
    issues:{listComments:'comments',createComment:async ({issue_number,body}) => {
      comments[issue_number].push({id:10,user:{type:'Bot'},body});
    }},repos:{createCommitStatus:async s => statuses.push(s),compareCommitsWithBasehead:async args => {
      calls.push(args);return {data:{files:ui,commits:[{sha:'d'.repeat(40)}],total_commits:1}};
    }}},paginate:async (method,args) => method === 'prs' ? prs.map(p => ({...p})) : comments[args.issue_number],
    graphql:async (query,args) => ({repository:{object:{oid:args.oid,authors:{totalCount:0,nodes:[]}}}})};
  const context = {repo:{owner:'test',repo:'test'},payload:{pull_request:{number:1}}};
  return {p,prs,comments,statuses,calls,github,context};
}
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
  f.github.rest.repos.getContent = async ({ref}) => {refs.push(ref);return {data:{encoding:'base64',size:50,content:Buffer.from('import SwiftUI\nstruct IntegrationNudgeCard: View {}').toString('base64')}};};
  await run(f);
  assert.equal(f.statuses.at(-1).state,'failure');
  assert.deepEqual(refs,[f.p.base.sha,f.p.head.sha]);
  f.github.rest.repos.getContent = async () => ({data:{encoding:'base64',size:40,content:Buffer.from('import Foundation\nclass Service {}').toString('base64')}});
  await run(f); assert.equal(f.statuses.at(-1).state,'success');
});

test('arbitrarily named AppKit panel requires approval', async () => {
  const f = fixture();
  f.github.rest.repos.compareCommitsWithBasehead = async () => ({data:{files:[{filename:'desktop/macos/Desktop/Sources/Chrome/CustomChrome.swift'}],commits:[],total_commits:0}});
  f.github.rest.repos.getContent = async () => ({data:{encoding:'base64',size:60,content:Buffer.from('import AppKit; class CustomChrome: NSPanel {}').toString('base64')}});
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
