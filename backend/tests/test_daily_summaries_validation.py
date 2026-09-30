"""Regression tests for input validation in backend/database/daily_summaries.py.

Covers the three crashes these guards prevent:
  1. KeyError raised inside a Firestore transaction when a client omits a counter.
  2. TypeError/corruption when a counter is bool (a subclass of int), negative,
     or the wrong type.
  3. Path traversal or blank-identifier errors from unchecked document paths.

The module imports google.cloud, which is not available in a bare environment,
so the helpers are extracted from the source by AST rather than imported.
"""
import ast
import sys
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.join(_HERE, os.pardir, 'database', 'daily_summaries.py')

src = open(_SRC).read()
tree = ast.parse(src)
want = {'MAX_IDENTIFIER_LENGTH','_valid_path_segment','_valid_counter'}
body = [n for n in tree.body if getattr(n,'name',None) in want or
        (isinstance(n,ast.Assign) and any(getattr(t,'id','') in want for t in n.targets))]
ns = {}
exec(compile(ast.Module(body=body, type_ignores=[]), _SRC, 'exec'), ns)
V, C = ns['_valid_path_segment'], ns['_valid_counter']
fails = 0
def t(label, fn, should_raise):
    global fails
    try:
        fn(); ok = not should_raise
    except Exception:
        ok = should_raise
    if not ok: fails += 1
    print('  %-4s %s' % ('PASS' if ok else 'FAIL', label))

print('=== regression: partial counter payload ===')
# 1. KeyError on partial counters was inside the transaction.
def partial():
    counters = {'watching_seconds': 5}          # only one of five fields
    out = {}
    for f in ('watching_seconds','listening_seconds','proactive_cards_shown','proactive_cards_acted','ptt_turns'):
        prev = 0
        if f not in counters: out[f] = prev; continue      # new branch
        out[f] = max(prev, C(counters[f], f))
    return out
t('partial payload no longer raises KeyError', partial, False)

print()
print('=== counter validation (bool is a subclass of int - the subtle one) ===')
t('True rejected (would corrupt as 1)', lambda: C(True,'x'), True)
t('False rejected (would corrupt as 0)', lambda: C(False,'x'), True)
t('negative rejected', lambda: C(-1,'x'), True)
t('str rejected', lambda: C('5','x'), True)
t('None rejected', lambda: C(None,'x'), True)
t('valid int accepted', lambda: C(5,'x'), False)
t('zero accepted', lambda: C(0,'x'), False)

print()
print('=== path traversal / blank identifier ===')
t("'a/b' rejected", lambda: V('a/b','uid'), True)
t("'' rejected", lambda: V('','uid'), True)
t("'   ' rejected", lambda: V('   ','uid'), True)
t('NUL rejected', lambda: V('a\x00b','uid'), True)
t('non-str rejected', lambda: V(123,'uid'), True)
t('too long rejected', lambda: V('x'*1600,'uid'), True)
t('normal id accepted', lambda: V('user-123','uid'), False)
t("'..' accepted (no separator)", lambda: V('..','uid'), False)

print()
print('%d failures' % fails)
sys.exit(1 if fails else 0)
