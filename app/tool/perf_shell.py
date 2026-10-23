#!/usr/bin/env python3
"""Materialize main.dart's actual shell without starting Firebase/native services.

Only the page, navigator key alias and analytics platform/key predicate differ.
Unknown source shapes fail closed. --check is part of both local and CI gates.
"""
import argparse
import hashlib
from pathlib import Path
import re

APP = Path(__file__).resolve().parents[1]
OUTPUT = APP / 'integration_test/perf/production_shell.dart'


def generate(source):
    build = source[source.index('  Widget build(BuildContext context) {', source.index('class _MyAppState')):]
    if not re.match(r'  Widget build\(BuildContext context\) \{\s*return MultiProvider\(', build):
        raise ValueError('Production root wrapper changed: extract a shared shell hook before accepting this shape')
    start = source.index('      builder: (context, child) {', source.index('class _MyAppState'))
    end = source.index('\n    );\n  }\n}', start)
    shell = source[start:end].strip()
    if not shell.endswith('},') or shell.count('MaterialApp(') != 1:
        raise ValueError('Production shell shape changed: expose a shared shell hook; never omit wrappers')
    field_start = source.index('  late final MobilePerformanceTelemetry _performanceTelemetry')
    field_end = source.index('\n\n', field_start)
    telemetry = source[field_start:field_end]
    substitutions = {
        'const AppShell()': 'widget.page',
        'PlatformService.isIOS && Env.posthogApiKey != null': 'widget.iosAnalytics',
    }
    for old, new in substitutions.items():
        if shell.count(old) != 1:
            raise ValueError(f'Production shell boundary changed: expected exactly one {old}')
        shell = shell.replace(old, new)
    imports = '\n'.join(re.findall(r'^import .*?;', source, re.M))
    digest = hashlib.sha256(source.encode()).hexdigest()
    return f'''// Derived by python3 tool/perf_shell.py from main.dart. Do not hand edit.
// Source shell SHA256: {digest}
// ignore_for_file: unused_import
{imports}
import 'package:omi/main.dart' show MyApp, CustomErrorWidget;

/// The exact production builder chain, with an inert seeded page boundary.
/// Force the iOS + configured analytics arm on hosts; no analytics keys required.
class PerfProductionShell extends StatefulWidget {{
  const PerfProductionShell({{super.key, required this.page, this.iosAnalytics = true}});
  final Widget page;
  final bool iosAnalytics;
  @override
  State<PerfProductionShell> createState() => _PerfProductionShellState();
}}
class _PerfProductionShellState extends State<PerfProductionShell> {{
{telemetry}
  @override
  void initState() {{
    super.initState();
    _performanceTelemetry.attach();
  }}
  @override
  void dispose() {{
    _performanceTelemetry.dispose();
    super.dispose();
  }}
  @override
  Widget build(BuildContext context) => MultiProvider(
    providers: [
      ChangeNotifierProvider(create: (_) => AppearanceProvider()),
      ChangeNotifierProvider(create: (_) => LocaleProvider()),
    ],
    {shell}
  );
}}
'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    expected = generate((APP / 'lib/main.dart').read_text())
    if args.check:
        # Dart format may change indentation, but cannot change tokens.
        if not OUTPUT.exists() or re.sub(r'\s+', '', OUTPUT.read_text()) != re.sub(r'\s+', '', expected):
            raise SystemExit('PERF RED: production shell drifted. Run python3 app/tool/perf_shell.py, review all new wrappers, then rerun the gate.')
        print('Production shell fidelity: PASS (source checked, iOS analytics enabled)')
    else:
        OUTPUT.write_text(expected)


if __name__ == '__main__':
    main()
