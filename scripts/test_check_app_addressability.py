#!/usr/bin/env python3
"""Hermetic tests of the constrained token scan, not widget behavior."""
import copy
import contextlib
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import check_app_addressability as check
import unittest

from check_app_addressability import calls, debt, validate_catalog, ROUTES


class AddressabilityCheckTests(unittest.TestCase):
    def test_nested_key_does_not_cover_interactive_parent(self):
        source = "InkWell(onTap: () {}, child: IconButton(key: OmiKeys.send, onPressed: () {}))"
        self.assertEqual(debt(source, {'send': 'omi.chat.send'}), ['InkWell'])

    def test_named_generic_constructors_and_multiline_arguments(self):
        source = """Switch.adaptive(key: const ValueKey('omi.chat.toggle'), onChanged: (_) {});
          DropdownButton<String>(key: OmiKeys.select, onChanged: (_) {});
          TextField(key: ValueKey(AddressKey.row('chat', opaqueId)));"""
        self.assertEqual(debt(source, {'select': 'omi.chat.select', 'toggle': 'omi.chat.toggle'}), [])

    def test_callback_comparison_does_not_hide_later_key(self):
        source = "IconButton(onPressed: () { if (x < y) doThing(); }, key: OmiKeys.send)"
        self.assertEqual(debt(source, {'send': 'omi.chat.send'}), [])

    def test_comments_strings_and_invalid_keys(self):
        self.assertEqual(debt('''// TextField()
          const note = "IconButton()"; /* Switch() */
          IconButton(key: ValueKey('other.send')); TextField(key: OmiKeys.unknown);''', {}),
                         ['IconButton', 'TextField'])

    def test_new_widgets_disabled_widgets_and_callback_body(self):
        self.assertEqual(debt("TextField(); IconButton(onPressed: null); InkWell(onTap: () { f(1, 2); });", {}),
                         ['TextField', 'IconButton', 'InkWell'])
        self.assertEqual(debt('ListTile(title: Text("heading")); GestureDetector(child: Text("x"));', {}), [])

    def test_navigation_calls_ignore_prose(self):
        self.assertEqual(len(list(calls('MaterialPageRoute<void>(builder: (_) => Page()); // pushNamed()', ROUTES))), 1)

    def test_new_page_and_unregistered_navigation_fail(self):
        catalog = dict(routes=[], keys={}, fixtures={}, deferred_pages=['app/lib/pages/old.dart'], navigation_sites={})
        self.assertEqual(validate_catalog(catalog, {'app/lib/pages/old.dart': 'class Old {}'}), [])
        errors = validate_catalog(catalog, {'app/lib/pages/new.dart': 'class New {}'})
        self.assertTrue(errors)
        for remedy in (check.CATALOG, 'routes entry', 'navigation_sites[file]', '--generate', 'ADDRESSABILITY.md'):
            self.assertIn(remedy, errors[0])
        self.assertTrue(validate_catalog(catalog, {'app/lib/pages/old.dart': 'MaterialPageRoute(builder: f)'}))

    def test_new_screen_in_old_file_cannot_hide_behind_page_file_inventory(self):
        catalog = dict(routes=[], keys={}, fixtures={}, deferred_pages=['app/lib/pages/old.dart'], navigation_sites={})
        source = 'class UnregisteredPage extends StatefulWidget {}'
        errors = validate_catalog(catalog, {'app/lib/pages/old.dart': source})
        self.assertEqual(len(errors), 1)
        self.assertIn('UnregisteredPage', errors[0])
        legacy = {**catalog, 'deferred_widgets': {'app/lib/pages/old.dart': ['UnregisteredPage']}}
        self.assertEqual(validate_catalog(legacy, {'app/lib/pages/old.dart': source}), [])
        self.assertTrue(check.inventory_growth(legacy, catalog))
        self.assertEqual(check.screen_classes('// class HiddenPage extends StatelessWidget {}'), set())

    def test_registry_cannot_claim_nonexistent_source_or_unknown_fixture(self):
        route = dict(id='chat', root='omi.chat.root', source='missing', reach={'kind': 'push'},
                     profile='local_dev', auth='signed_in', fixture='unknown', widget='ChatPage', ready_provider='messages')
        catalog = dict(routes=[route], keys={'root': 'omi.chat.root'}, fixtures={}, deferred_pages=[], navigation_sites={})
        self.assertEqual(len(validate_catalog(catalog, {})), 2)
        duplicate = copy.deepcopy(catalog)
        duplicate['routes'].append(route)
        self.assertIn('duplicate route/root: chat', validate_catalog(duplicate, {}))

    def test_inventory_debt_can_shrink_but_new_sites_need_route_ids(self):
        previous = dict(deferred_pages=['old'], navigation_sites={'old': ['legacy:1']})
        self.assertEqual(check.inventory_growth(previous, previous), [])
        self.assertEqual(check.inventory_growth(dict(deferred_pages=[], navigation_sites={}), previous), [])
        added = dict(deferred_pages=['old', 'new'], navigation_sites={'old': ['legacy:1', 'legacy:2']})
        self.assertEqual(len(check.inventory_growth(added, previous)), 2)

    def test_only_changed_files_are_held_to_debt_and_baseline_cannot_increase(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = 'app/lib/widgets/old.dart'
            (root / path).parent.mkdir(parents=True)
            (root / path).write_text('TextField(); TextField();')
            catalog = dict(routes=[], keys={'input': 'omi.chat.input'}, fixtures={}, deferred_pages=[], navigation_sites={})
            for filename, value in [(check.CATALOG, catalog), (check.BASELINE, {path: 1})]:
                (root / filename).parent.mkdir(parents=True, exist_ok=True)
                (root / filename).write_text(json.dumps(value))
            (root / check.GENERATED).parent.mkdir(parents=True)
            (root / check.GENERATED).write_text(check.generated(catalog))
            changes = root / 'changes'
            changes.write_text('unrelated.dart')
            def base(_ref, filename):
                if filename == check.CATALOG: return json.dumps(catalog)
                if filename == check.BASELINE: return json.dumps({path: 1})
                return 'TextField();'
            with patch.object(check, 'ROOT', root), patch.object(check, 'read_base', base), \
                 patch.object(check.subprocess, 'check_output', return_value=path), \
                 patch('sys.argv', ['check', '--changed-files', str(changes)]), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(check.main(), 0)
                changes.write_text(path)
                self.assertEqual(check.main(), 1)
                (root / path).write_text("TextField(key: ValueKey('omi.chat.input'));")
                self.assertEqual(check.main(), 0)
                (root / check.BASELINE).write_text(json.dumps({path: 2}))
                self.assertEqual(check.main(), 1)

    def test_catalog_identity_uses_existing_harness_and_journey_fixture(self):
        catalog = json.loads((check.ROOT / check.CATALOG).read_text())
        fixture = json.loads((check.ROOT / catalog['identity_fixture']).read_text())
        uid = fixture['auth']['users'][fixture['auth']['default_user_index']]['uid']
        backend = (check.ROOT / catalog['fixture_backend']).read_text()
        self.assertIn("fixtureUid = '" + uid + "'", backend)
        for value in catalog['fixtures'].values():
            self.assertIn(value['uid'], (None, uid))
        self.assertIn('seeded-conv-j1-0001', catalog['fixtures']['conversation-one']['records'])


if __name__ == '__main__':
    unittest.main()
