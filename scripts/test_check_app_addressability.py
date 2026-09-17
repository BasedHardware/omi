#!/usr/bin/env python3
"""Hermetic tests of the constrained token scan, not widget behavior."""
import contextlib
import io
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import check_app_addressability as check
import unittest

from check_app_addressability import calls, debt, validate_catalog


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

    def test_helpers_dialogs_and_unmarked_screens_are_not_inventoried(self):
        catalog = dict(routes=[], keys={}, fixtures={}, controls={}, interactive_widgets=check.INTERACTIVE)
        for source in ['class ProbeHelper {}', 'showDialog(builder: f)', 'showModalBottomSheet(builder: f)',
                       'class ConfirmationSheet extends StatelessWidget {}', 'class NewPage extends StatefulWidget {}']:
            self.assertEqual(validate_catalog(catalog, {'app/lib/pages/new.dart': source}), [])

    def test_explicit_route_declaration_requires_registration_with_actionable_remedy(self):
        catalog = dict(routes=[], keys={}, fixtures={}, controls={}, interactive_widgets=check.INTERACTIVE)
        errors = validate_catalog(catalog, {'app/lib/pages/new.dart': '// omi-route: new_screen\nclass NewScreen {}'})
        self.assertEqual(len(errors), 1)
        for remedy in (check.CATALOG, 'routes entry', 'controls[route_id]', '--generate', 'ADDRESSABILITY.md'):
            self.assertIn(remedy, errors[0])

    def test_catalog_validation_does_not_require_untouched_route_source(self):
        catalog = json.loads((check.ROOT / check.CATALOG).read_text())
        self.assertEqual(validate_catalog(catalog, {'app/lib/pages/helper.dart': 'class Helper {}'}), [])
        route = catalog['routes'][0]
        self.assertTrue(validate_catalog(catalog, {route['source']: 'class WrongPage {}'}))

    def test_surface_acceptance_does_not_zero_directory_debt(self):
        catalog = json.loads((check.ROOT / check.CATALOG).read_text())
        route = next(r for r in catalog['routes'] if r['id'] == 'chat')
        sources = {route['source']: '// omi-route: chat\nTextField(key: OmiKeys.chatInput); GestureDetector(key: OmiKeys.chatSend); TextField();',
                   'app/lib/pages/chat/unrelated.dart': 'TextField();' * 300}
        self.assertEqual(check.surface_errors(catalog, 'chat', sources), [])
        sources[route['source']] = '// omi-route: chat\nTextField(key: OmiKeys.chatInput);'
        self.assertTrue(check.surface_errors(catalog, 'chat', sources))

    def test_constructor_vocabulary_is_generated_from_one_catalog(self):
        catalog = json.loads((check.ROOT / check.CATALOG).read_text())
        generated = check.generated_interactive(catalog)
        self.assertEqual(set(check.INTERACTIVE), set(catalog['interactive_widgets']))
        for name, callbacks in check.INTERACTIVE.items():
            self.assertIn(f'widget is {name})', generated)
            args = '' if callbacks is None else f'{callbacks[0]}: () {{}}'
            self.assertEqual(debt(f'{name}({args})', {}), [name])
        self.assertEqual((check.ROOT / check.INTERACTIVE_GENERATED).read_text(), generated)

    def test_legacy_growth_passes_but_adopted_debt_and_adoption_cannot_regress(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = 'app/lib/widgets/old.dart'
            (root / path).parent.mkdir(parents=True)
            (root / path).write_text('TextField(); TextField();')
            catalog = dict(routes=[], keys={'input': 'omi.chat.input'}, fixtures={}, controls={}, interactive_widgets=check.INTERACTIVE)
            for filename, value in [(check.CATALOG, catalog), (check.BASELINE, {path: 1}), (check.ADOPTED, [])]:
                (root / filename).parent.mkdir(parents=True, exist_ok=True)
                (root / filename).write_text(json.dumps(value))
            (root / check.GENERATED).parent.mkdir(parents=True)
            (root / check.GENERATED).write_text(check.generated(catalog))
            (root / check.INTERACTIVE_GENERATED).parent.mkdir(parents=True, exist_ok=True)
            (root / check.INTERACTIVE_GENERATED).write_text(check.generated_interactive(catalog))
            changes = root / 'changes'
            changes.write_text('unrelated.dart')
            prior_adopted = []
            def base(_ref, filename):
                if filename == check.ADOPTED: return json.dumps(prior_adopted)
                if filename == check.CATALOG: return json.dumps(catalog)
                if filename == check.BASELINE: return json.dumps({path: 1})
                return 'TextField();'
            with patch.object(check, 'ROOT', root), patch.object(check, 'read_base', base), \
                 patch.object(check.subprocess, 'check_output', return_value=path), \
                 patch('sys.argv', ['check', '--changed-files', str(changes)]), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(check.main(), 0)
                changes.write_text(path)
                self.assertEqual(check.main(), 0)  # ordinary legacy growth is allowed
                (root / check.ADOPTED).write_text(json.dumps([path]))
                self.assertEqual(check.main(), 1)
                prior_adopted.append(path)
                (root / path).write_text("TextField(key: ValueKey('omi.chat.input'));")
                self.assertEqual(check.main(), 0)
                (root / check.BASELINE).write_text(json.dumps({path: 2}))
                self.assertEqual(check.main(), 1)
                (root / check.BASELINE).write_text(json.dumps({path: 1}))
                (root / check.ADOPTED).write_text('[]')
                self.assertEqual(check.main(), 1)  # adoption cannot be undone

    def test_default_scan_ignores_incoming_main_changes_but_includes_untracked_helpers(self):
        import subprocess
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            def git(*args):
                return subprocess.check_output(['git', '-C', str(root), *args], text=True)
            git('init', '-q')
            git('config', 'user.name', 'Fixture')
            git('config', 'user.email', 'fixture@example.test')
            catalog = dict(routes=[], keys={}, fixtures={}, controls={}, interactive_widgets=check.INTERACTIVE)
            path = 'app/lib/pages/old.dart'
            for filename, content in [(check.CATALOG, json.dumps(catalog)), (check.BASELINE, json.dumps({path: 1})),
                                      (check.ADOPTED, '[]'),
                                      (check.GENERATED, check.generated(catalog)),
                                      (check.INTERACTIVE_GENERATED, check.generated_interactive(catalog)),
                                      (path, 'TextField();')]:
                file = root / filename
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_text(content)
            git('add', '.')
            git('commit', '-qm', 'shared base')
            git('branch', 'fixture-task')
            (root / path).write_text('')
            git('add', '.')
            git('commit', '-qm', 'incoming main retires debt')
            git('update-ref', 'refs/remotes/origin/main', 'HEAD')
            git('switch', '-q', 'fixture-task')
            helper = root / 'app/lib/pages/helper.dart'
            helper.write_text('class Helper {}')
            with patch.object(check, 'ROOT', root), patch('sys.argv', ['check']), \
                 contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(check.main(), 0)
                helper.write_text('IconButton(onPressed: () {});')
                self.assertEqual(check.main(), 1)  # a brand-new file starts without key debt
                helper.write_text('// omi-route: missing\nclass MissingPage extends StatelessWidget {}')
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
