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
test('workflow blocks, deduplicates, approves and revokes on the same API path', async () => {
  const run = require('../ui-author-approval.cjs');
  const p = {...pr,user:actor,state:'open',base:{ref:'main'}};
  const comments = [];
  const statuses = [];
  const pulls = {get:async () => ({data:p}),listFiles:'files',listCommits:'commits'};
  const github = {rest:{pulls,issues:{listComments:'comments',createComment:async ({body}) => {
    comments.push({id:10,user:{type:'Bot'},body});
  }},repos:{createCommitStatus:async s => statuses.push(s)}},
  paginate:async method => ({files:ui,commits:[],comments})[method],
  graphql:async () => ({repository:{pullRequest:{commits:{nodes:[],pageInfo:{hasNextPage:false}}}}})};
  const context = {repo:{owner:'test',repo:'test'},payload:{pull_request:{number:1}}};
  await run({github,context});
  await run({github,context});
  await run({github,context});
  assert.equal(comments.length,1);
  assert.ok(comments[0].body.includes('@kodjima33'));
  assert.equal(statuses.at(-1).state,'failure');
  comments.push(approve);
  await run({github,context});
  assert.equal(statuses.at(-1).state,'success');
  comments.pop();
  await run({github,context});
  assert.equal(statuses.at(-1).state,'failure');
  p.head = {sha:'b'.repeat(40)};
  comments.push(approve);
  await run({github,context});
  assert.equal(statuses.at(-1).state,'failure');
  assert.equal(comments.filter(c => c.user.type === 'Bot').length,2);
  github.graphql = async () => {throw new Error('API failure');};
  await assert.rejects(run({github,context}),/API failure/);
  assert.equal(statuses.at(-1).state,'failure');
});
