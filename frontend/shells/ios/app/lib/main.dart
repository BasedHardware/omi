// Minimal Flutter shell hosting a TS surface in a platform webview.
// Mirrors ADR-002: the shell owns device/capture state, the surface is UI only,
// and everything crossing the boundary goes through the generated bridge.
import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';

import 'bridge_http_host.dart';
import 'gen/bridge.g.dart';
import 'gen/bridge_http_contract.g.dart';
import 'listen_socket_host.dart';
import 'loop_server.dart';
import 'scheme_host.dart';

/// Where the surface is loaded from.
/// ship   = bundled asset (what an App Store build does)
/// dev    = local dev server (live reload of the surface, no Dart rebuild)
/// loop   = in-app loopback HTTP server (ship-origin candidate A probe)
/// scheme = native WKURLSchemeHandler at omi-ui://local (candidate B / wave-2)
enum SurfaceMode { ship, dev, loop, scheme }

// Set at build time: flutter run --dart-define=SURFACE_MODE=dev
const String _modeFlag = String.fromEnvironment('SURFACE_MODE', defaultValue: 'ship');
// iOS simulator can reach the host Mac on localhost; a real device needs the LAN IP.
const String _devHost = String.fromEnvironment('SURFACE_HOST', defaultValue: 'localhost:8787');
// loop mode: 0 = ephemeral port (demonstrates origin-per-port storage loss),
// any fixed value = stable origin across relaunches.
const int _loopPort = int.fromEnvironment('LOOP_PORT', defaultValue: 0);
// scheme mode: which Documents/bundles/<id> to mount. Wave-2 default is the
// real @omi-core/surfaces ship build; set SCHEME_BUNDLE=v1 to re-run the probe.
const String _schemeBundle = String.fromEnvironment('SCHEME_BUNDLE', defaultValue: 'surfaces');
// AUTODRIVE task text for the real surfaces harness (blank = open only).
const String _addTask = String.fromEnvironment('ADD_TASK', defaultValue: '');
// Privileged-HTTP custody (wave 9): the SHELL holds the API base URL and bearer
// token; neither is ever handed to the webview. Unset base URL => no channel
// registered => the surface truthfully feature-detects "no bridge" and falls
// back to its DEV transport. Dev-grade custody (keychain is owed).
const String _apiBaseUrl = String.fromEnvironment('OMI_API_BASE_URL', defaultValue: '');
const String _apiToken = String.fromEnvironment('OMI_API_TOKEN', defaultValue: '');
// Optional scheme query/profile namespace. Values are appended to the local
// scheme URL, never interpolated into page JavaScript or logs.
const String _surfaceQuery = String.fromEnvironment('SURFACE_QUERY', defaultValue: '');
const String _surfaceProfile = String.fromEnvironment('SURFACE_PROFILE', defaultValue: '');
const bool _acceptance = bool.fromEnvironment('OMI_ACCEPTANCE', defaultValue: false);
const bool _acceptanceExit = bool.fromEnvironment('OMI_ACCEPTANCE_EXIT', defaultValue: false);

void main() => runApp(const ProtoApp());

class ProtoApp extends StatelessWidget {
  const ProtoApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Omi webview proto',
      debugShowCheckedModeBanner: false,
      theme: ThemeData.dark(useMaterial3: true),
      home: const SurfaceHost(),
    );
  }
}

class SurfaceHost extends StatefulWidget {
  const SurfaceHost({super.key});

  @override
  State<SurfaceHost> createState() => _SurfaceHostState();
}

class _SurfaceHostState extends State<SurfaceHost> with WidgetsBindingObserver implements OmiShellBridgeHandler {
  late final WebViewController _controller;
  late final OmiShellBridge _bridge;
  BridgeHttpHost? _http;
  ListenSocketHost? _listen;
  Timer? _transcriptTimer;
  Timer? _acceptanceFallback;
  int _sessions = 0;
  // loop mode: two servers so one run demonstrates origin-per-port isolation.
  LoopServer? _loopA, _loopB;
  int _loopPhase = 0;
  // scheme mode: phase machine driving bundle swap / gate / suspend probes.
  SchemeSpike? _scheme;
  int _schemePhase = 0;
  String? _blocked; // non-null = contract gate refused the mount (error surface)
  bool _acceptanceEmitted = false;

  String get _surfaceQuerySuffix {
    var raw = _surfaceQuery.trim();
    if (raw.startsWith('?')) raw = raw.substring(1);
    final params = <String, String>{};
    if (raw.isNotEmpty) {
      try {
        params.addAll(Uri.splitQueryString(raw.split('#').first));
      } on FormatException {
        // A malformed optional query must not make the shell fail to boot.
      }
    }
    if (_surfaceProfile.trim().isNotEmpty) {
      params['profile'] = _surfaceProfile.trim();
    }
    if (params.isEmpty) return '';
    return '?${Uri(queryParameters: params).query}';
  }

  String _redactedUrl(String? raw) {
    final parsed = Uri.tryParse(raw ?? '');
    return parsed?.replace(query: '', fragment: '', userInfo: '').toString() ?? '(invalid-url)';
  }

  Future<void> _emitAcceptance(String phase) async {
    if ((!_acceptance && !_acceptanceExit) || _acceptanceEmitted) return;
    final served = _http?.servedCount ?? 0;
    // Ready is a page lifecycle hint, not proof that the async store refresh
    // reached the host. Wait for host-observed traffic, or let the bounded
    // fallback below produce a real failure.
    if (served == 0 && phase != 'ready-timeout' && phase != 'autodrive') {
      _acceptanceFallback ??= Timer(const Duration(seconds: 5), () {
        _acceptanceFallback = null;
        unawaited(_emitAcceptance('ready-timeout'));
      });
      return;
    }
    _acceptanceFallback?.cancel();
    _acceptanceFallback = null;
    _acceptanceEmitted = true;
    final line =
        'ACCEPTANCE phase=$phase bridge=${_http == null ? 'disabled' : 'enabled'} '
        'servedCount=$served profileProvided=${_surfaceProfile.trim().isNotEmpty} '
        'status=${served > 0 ? 'PASS' : 'FAIL'}';
    debugPrint(line);
    await _scheme?.log(line, echo: false);
    if (_acceptanceExit) exit(served > 0 ? 0 : 1);
  }

  SurfaceMode get _mode => switch (_modeFlag) {
    'dev' => SurfaceMode.dev,
    'loop' => SurfaceMode.loop,
    'scheme' => SurfaceMode.scheme,
    _ => SurfaceMode.ship,
  };

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    // Privileged HTTP: register BEFORE any load so the page sees the channel on
    // its first script evaluation and picks bridge mode rather than DEV.
    final apiBase = Uri.tryParse(_apiBaseUrl);
    if (_apiBaseUrl.isNotEmpty && apiBase != null && apiBase.hasScheme && apiBase.host.isNotEmpty) {
      final authority = ShellTransportAuthority(baseUrl: apiBase, token: _apiToken);
      _http = authority.makeHttpHost();
      _listen = authority.makeListenHost();
      debugPrint(
        '[bridge-http] enabled for ${apiBase.scheme}://${apiBase.host} '
        '(token ${_http!.hasCredential ? "present" : "absent"})',
      );
    } else {
      debugPrint('[bridge-http] disabled (set OMI_API_BASE_URL to enable privileged HTTP)');
    }
    _controller = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(const Color(0xFF0B0B0F))
      // Surface console -> flutter logs, so headless runs can read bench output.
      ..setOnConsoleMessage((msg) {
        debugPrint('[surface] ${msg.message}');
        _scheme?.log('[surface] ${msg.message}', echo: false);
        if (msg.message.contains('OMI_PRODUCTION_READY') ||
            msg.message.contains('data-surface-state=ready') ||
            msg.message.contains('data-surface-state="ready"')) {
          unawaited(_emitAcceptance('surface-ready'));
        }
        if (msg.message.contains('PROBE all-done')) {
          if (_mode == SurfaceMode.scheme) {
            _onSchemePhaseDone();
          } else {
            _onLoopPhaseDone();
          }
        }
      })
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageFinished: (url) {
            _scheme?.log('PAGE-FINISHED ${_redactedUrl(url)}');
            if (const bool.fromEnvironment('AUTODRIVE')) {
              unawaited(_autodrive());
            } else {
              if (_acceptance || _acceptanceExit) {
                // Surface store refresh is asynchronous; page-finished alone is
                // not evidence of bridge traffic. The marker above wins, while
                // this bounded fallback keeps a hung surface fail-capable.
                _acceptanceFallback ??= Timer(const Duration(seconds: 5), () {
                  _acceptanceFallback = null;
                  unawaited(_emitAcceptance('ready-timeout'));
                });
              }
            }
          },
          onWebResourceError: (e) {
            _scheme?.log('WEB-RESOURCE-ERROR ${e.errorCode} ${e.description} ${_redactedUrl(e.url)}');
          },
        ),
      );
    _bridge = OmiShellBridge(_controller, this);
    _boot();
  }

  // Lifecycle probes for the suspension-resilience question: log every
  // transition, and on resume verify from inside the page that (a) the DOM is
  // alive, (b) storage is readable, (c) the scheme handler still serves, and
  // (d) the bridge still round-trips.
  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    _scheme?.log('LIFECYCLE $state');
    if (state == AppLifecycleState.resumed && _mode == SurfaceMode.scheme && _schemePhase > 0) {
      _controller.runJavaScript(
        "console.log('PROBE resume readyState='+document.readyState+' bootCount='+localStorage.getItem('bootCount'));"
        "fetch('/probe/echo?after=resume').then(r=>console.log('PROBE resume-fetch '+r.status)).catch(e=>console.log('PROBE resume-fetch FAIL '+e));"
        "if(window.__probeBridge){var t=Date.now();window.__probeBridge.getDeviceState().then(()=>console.log('PROBE resume-bridge-rtt '+(Date.now()-t)+'ms')).catch(e=>console.log('PROBE resume-bridge FAIL '+e));}",
      );
    }
  }

  Future<void> _boot() async {
    await _bridge.attach();
    // Register privileged HTTP before the first load: the surface's feature
    // detection runs on its first script evaluation, so a channel added after
    // navigation would leave it in DEV mode for the life of the page.
    await _http?.register(_controller);
    await _listen?.register(_controller);
    switch (_mode) {
      case SurfaceMode.dev:
        await _controller.loadRequest(Uri.parse('http://$_devHost/'));
      case SurfaceMode.loop:
        _loopA = LoopServer('assets/surface-loop');
        await _loopA!.start(port: _loopPort);
        _loopPhase = 1;
        debugPrint('[loop] phase 1: loading from port ${_loopA!.port}');
        await _controller.loadRequest(Uri.parse('http://127.0.0.1:${_loopA!.port}/'));
      case SurfaceMode.scheme:
        _scheme = SchemeSpike();
        await _scheme!.init();
        await _scheme!.log(
          'BOOT scheme mode, shell contract $kBridgeContractVersion, '
          'bundle=$_schemeBundle, bundles installed under ${_scheme!.docsDir}/bundles',
        );
        // Probe phase machine only for the original v1/v2/v3 suite.
        _schemePhase = _schemeBundle == 'v1' ? 1 : 0;
        await _mountBundle(_schemeBundle);
      case SurfaceMode.ship:
        // Asset mode: file:// origin, allowed to read sibling assets in the bundle.
        await _controller.loadFlutterAsset('assets/surface/index.html');
    }
  }

  /// Gate-then-navigate. Returns false when the contract gate refused the
  /// bundle (navigation is never attempted — the webview keeps whatever it was
  /// showing and the shell raises the error surface).
  Future<bool> _mountBundle(String version) async {
    final s = _scheme!;
    final gate = await s.gateCheck(version, kBridgeContractVersion);
    if (!gate.ok) {
      await s.log(
        'GATE-BLOCKED bundle=$version bundleId=${gate.bundleId} '
        'bundleContract=${gate.bundleContract} shellContract=$kBridgeContractVersion '
        '— navigation NOT attempted',
      );
      setState(
        () => _blocked =
            'Bundle "$version" refused: it requires bridge contract '
            '${gate.bundleContract}, this shell speaks $kBridgeContractVersion.',
      );
      return false;
    }
    await s.setActiveBundle(version);
    setState(() => _blocked = null);
    final target = 'omi-ui://local/index.html$_surfaceQuerySuffix';
    await s.log(
      'NAVIGATE bundle=$version -> omi-ui://local/index.html '
      'queryPresent=${_surfaceQuerySuffix.isNotEmpty}',
    );
    await _controller.loadRequest(Uri.parse(target));
    return true;
  }

  // Phase machine, advanced by the surface's `PROBE all-done` console line:
  //  1  v1 probe suite done            -> swap to v2 (update simulation)
  //  2  v2 done (storage must survive) -> attempt v3 (contract mismatch: must
  //     be refused before navigation), then roll back to v2
  //  4  rollback v2 done               -> SPIKE-DONE; open the suspend window
  //  5  post-suspend-window navigation done
  Future<void> _onSchemePhaseDone() async {
    final s = _scheme!;
    await s.drainSchemeLog();
    switch (_schemePhase) {
      case 1:
        await s.log('PHASE 1 complete (v1). Swapping bundle dir to v2 and reloading.');
        _schemePhase = 2;
        await _mountBundle('v2');
      case 2:
        await s.log('PHASE 2 complete (v2 after swap). Attempting v3 (bad contract).');
        _schemePhase = 3;
        final mounted = await _mountBundle('v3');
        await s.log(
          mounted
              ? 'PHASE 3 UNEXPECTED: v3 mounted despite contract mismatch'
              : 'PHASE 3 ok: v3 refused by gate; error surface shown. Rolling back to v2 in 2s.',
        );
        await Future<void>.delayed(const Duration(seconds: 2));
        _schemePhase = 4;
        await _mountBundle('v2');
      case 4:
        await s.log(
          'PHASE 4 complete (v2 rollback remount). SPIKE-DONE. '
          'Opening suspend window: will renavigate to v1 in 3s — background the app '
          'right after the SUSPEND-WINDOW line to test suspension mid-navigation.',
        );
        _schemePhase = 5;
        await Future<void>.delayed(const Duration(seconds: 3));
        await s.log('SUSPEND-WINDOW navigating v1 now');
        await _mountBundle('v1');
      case 5:
        await s.log(
          'PHASE 5 complete: navigation opened in the suspend window '
          'finished and the probe suite ran. SUSPEND-NAV-COMPLETE.',
        );
      default:
        await s.log('PROBE all-done in unexpected phase $_schemePhase');
    }
  }

  // After the probe suite finishes on server A, reload the identical bundle
  // from a second server on a different port: same app, same webview, same
  // bundle — if localStorage/IndexedDB come back empty, storage is keyed on
  // the port and an ephemeral-port design silently wipes user state.
  Future<void> _onLoopPhaseDone() async {
    if (_mode != SurfaceMode.loop || _loopPhase != 1 || _loopPort != 0) {
      if (_loopPhase == 2) debugPrint('[loop] phase 2 complete — compare bootCount/rows between phases');
      return;
    }
    _loopPhase = 2;
    _loopB = LoopServer('assets/surface-loop');
    await _loopB!.start(port: 0);
    debugPrint('[loop] phase 2: reloading from port ${_loopB!.port} (was ${_loopA!.port})');
    await _controller.loadRequest(Uri.parse('http://127.0.0.1:${_loopB!.port}/'));
  }

  // AUTODRIVE custody probes for the privileged-HTTP bridge (wave 9), mirroring
  // the macOS wave-7 set. PROTOTYPE-ONLY SCAFFOLDING: this drives the raw channel
  // with deliberately hostile inputs and must never exist on a production path
  // (see the playbook's AUTODRIVE note).
  //
  // The probe posts raw contract messages so it can attempt things the HttpClient
  // seam cannot express (forged headers, off-origin paths). It chains the
  // surface's own reply sink rather than replacing it, so the harness keeps
  // working while the probe runs.
  Future<void> _autodriveBridgeProbes() async {
    await _controller.runJavaScript(
      r"""
      window.__w9 = (function () {
        var pend = new Map();
        var prev = window.__omiHttpReply;
        window.__omiHttpReply = function (id, json) {
          if (pend.has(id)) {
            var res = pend.get(id); pend.delete(id);
            try { res(JSON.parse(json)); } catch (e) { res({ parseError: String(e) }); }
            return;
          }
          if (typeof prev === 'function') return prev(id, json);
        };
        var n = 0;
        return {
          call: function (msg) {
            return new Promise(function (res) {
              n += 1;
              var id = 'w9-' + n;
              pend.set(id, res);
              setTimeout(function () {
                if (pend.has(id)) { pend.delete(id); res({ timeout: true }); }
              }, 8000);
              msg.id = id;
              window[%CHANNEL%].postMessage(JSON.stringify(msg));
            });
          },
        };
      })();
      console.log('W9 probe-ready channelPresent=' + !!window[%CHANNEL%] +
        ' transport=' + ((document.querySelector('[data-transport]') || {}).getAttribute
          ? document.querySelector('[data-transport]').getAttribute('data-transport') : 'none'));
    """
          .replaceAll('%CHANNEL%', "'${BridgeHttpContract.channel}'"),
    );
    await Future<void>.delayed(const Duration(milliseconds: 400));

    await _controller.runJavaScript(r"""
      (async function () {
        var r = await window.__w9.call({ method: 'GET', path: '/w9/forged',
          headers: { authorization: 'Bearer HACKED', cookie: 'a=b', 'x-forged': 'yes' } });
        console.log('W9 forged-headers -> ' + JSON.stringify(r));
        r = await window.__w9.call({ method: 'GET', path: 'https://evil.example/steal' });
        console.log('W9 absolute-url -> ' + JSON.stringify(r));
        r = await window.__w9.call({ method: 'GET', path: '//evil.example/steal' });
        console.log('W9 protocol-relative -> ' + JSON.stringify(r));
        r = await window.__w9.call({ method: 'GET', path: '/w9/429' });
        console.log('W9 retry-after -> ' + JSON.stringify(r));
        r = await window.__w9.call({ method: 'POST', path: '/w9/post', body: JSON.stringify({ hello: 'world' }) });
        console.log('W9 post-body -> ' + JSON.stringify(r));
      })();
    """);
    await Future<void>.delayed(const Duration(milliseconds: 3000));

    // Custody: nothing secret may be reachable from the page.
    await _controller.runJavaScript(r"""
      (async function () {
        var keys = Object.keys(localStorage);
        var blob = keys.map(function (k) { return k + '=' + localStorage.getItem(k); }).join('|');
        var hits = [];
        if (blob.indexOf('dev-token-w9') >= 0) hits.push('localStorage:TOKEN');
        try {
          var names = (await indexedDB.databases()).map(function (d) { return d.name; });
          for (var i = 0; i < names.length; i++) {
            var db = await new Promise(function (res, rej) {
              var q = indexedDB.open(names[i]);
              q.onsuccess = function () { res(q.result); };
              q.onerror = function () { rej(q.error); };
            });
            var stores = Array.prototype.slice.call(db.objectStoreNames);
            for (var j = 0; j < stores.length; j++) {
              var rows = await new Promise(function (res, rej) {
                var t = db.transaction(stores[j], 'readonly');
                var q2 = t.objectStore(stores[j]).getAll();
                q2.onsuccess = function () { res(q2.result); };
                q2.onerror = function () { rej(q2.error); };
              });
              var s = JSON.stringify(rows);
              if (s.indexOf('dev-token-w9') >= 0) hits.push(names[i] + '/' + stores[j] + ':TOKEN');
              if (s.toLowerCase().indexOf('authorization') >= 0) hits.push(names[i] + '/' + stores[j] + ':AUTHHEADER');
            }
            db.close();
          }
          console.log('W9 custody dbs=' + names.length + ' lsKeys=' + JSON.stringify(keys) +
            ' cookie=' + JSON.stringify(document.cookie) + ' HITS=' + (hits.length ? JSON.stringify(hits) : 'NONE'));
        } catch (e) {
          console.log('W9 custody scan-error=' + e + ' HITS=' + (hits.length ? JSON.stringify(hits) : 'NONE'));
        }
      })();
    """);
    await Future<void>.delayed(const Duration(milliseconds: 2500));
    await _scheme?.log('W9-PROBES-DONE served=${_http?.servedCount}');
  }

  // Drives the surface from the shell so an unattended run still produces
  // numbers / screenshots: flutter run --dart-define=AUTODRIVE=true
  // For the real surfaces harness (SCHEME_BUNDLE=surfaces): click "Open harness",
  // then walk all four domain tabs. ADD_TASK non-empty seeds one row per
  // writable domain; leave it blank on relaunch to prove persistence without
  // writing. Every step reports through console.log, which setOnConsoleMessage
  // forwards to the Flutter log, so an unattended run is machine-checkable.
  //
  // The harness is multi-domain as of wave 6 (tasks | memories | conversations |
  // folders). Conversations is server-originated and has NO client create, so it
  // is observed (list renders, no create form) rather than written.
  Future<void> _autodrive() async {
    debugPrint('[autodrive] start mode=${_mode.name} bundle=$_schemeBundle addTask=$_addTask');
    if (_mode == SurfaceMode.scheme && _schemeBundle == 'surfaces') {
      await Future<void>.delayed(const Duration(milliseconds: 600));
      // Prefer the production-shell contract markers; retain the dev harness
      // class fallback so the existing probe remains runnable.
      await _controller.runJavaScript(r'''
        (function () {
          if (document.querySelector('[data-production-shell] [data-route]') ||
              document.querySelector('nav.dev-tabs')) {
            console.log('AUTODRIVE open-harness ALREADY'); return;
          }
          var btn = document.querySelector(
            '[data-production-shell] [data-action="open-harness"], ' +
            '[data-production-shell] [data-route="harness"]');
          if (!btn) btn = document.querySelector('.dev-connect > button');
          if (btn) { btn.click(); console.log('AUTODRIVE open-harness'); }
          else { console.log('AUTODRIVE open-harness MISSING'); }
        })();
      ''');
      await Future<void>.delayed(const Duration(milliseconds: 1400));
      // Install shared tab/list helpers once, then drive each domain.
      await _controller.runJavaScript(r'''
        (function () {
          window.__ad = {
            lists: { tasks: 'ul.task-list', memories: 'ul.memory-list',
                     conversations: 'ul.conversation-list', folders: 'ul.folder-list' },
            root: function () {
              return document.querySelector('[data-production-shell]') || document;
            },
            list: function (route) {
              var root = window.__ad.root();
              var generic = root.querySelector(
                '[data-route="' + route + '"][data-surface-state="list"], ' +
                '[data-route="' + route + '"] [data-surface-state="list"]');
              return generic || root.querySelector(window.__ad.lists[route]);
            },
            rows: function (route) {
              var list = window.__ad.list(route);
              var ul = list || window.__ad.root();
              var marked = ul.querySelectorAll('[data-surface-state="row"]');
              if (marked.length) return marked.length;
              if (!list) return -1;
              return Array.prototype.filter.call(list.querySelectorAll('li'),
                function (li) { return !li.classList.contains('empty'); }).length;
            },
            openTab: function (route) {
              var root = window.__ad.root();
              var b = root.querySelector(
                'button[data-route="' + route + '"], a[data-route="' + route + '"], ' +
                '[role="tab"][data-route="' + route + '"], ' +
                '[data-action="navigate"][data-route="' + route + '"]');
              if (!b) {
                var order = ['tasks', 'memories', 'conversations', 'folders'];
                var buttons = root.querySelectorAll('nav.dev-tabs button');
                var index = order.indexOf(route);
                b = index >= 0 ? buttons[index] : null;
              }
              if (b) { b.click(); return true; }
              return false;
            },
            seed: function (route, text) {
              if (window.__ad.rows(route) > 0) return 'SKIP already=' + window.__ad.rows(route);
              var root = window.__ad.root();
              var form = root.querySelector('form[data-action="create"], [data-action="create"] form, form.add-row');
              if (!form) {
                var trigger = root.querySelector('[data-action="create"]');
                form = trigger && trigger.closest ? trigger.closest('form') : null;
              }
              if (!form) return 'NO_CREATE_FORM';
              var field = form.querySelector('[data-field="text"], input, textarea');
              if (!field) return 'NO_FIELD';
              var proto = field.tagName === 'TEXTAREA'
                ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype;
              Object.getOwnPropertyDescriptor(proto, 'value').set.call(field, text);
              field.dispatchEvent(new Event('input', { bubbles: true }));
              var btn = form.querySelector('[data-action="submit"], button[type="submit"]');
              if (btn && !btn.disabled) btn.click();
              else if (form.requestSubmit) form.requestSubmit();
              else return 'SUBMIT_UNAVAILABLE';
              return 'submitted';
            },
          };
          console.log('AUTODRIVE helpers-ready routes=' +
            ['tasks', 'memories', 'conversations', 'folders'].join('|'));
        })();
      ''');
      final seedText = _addTask.replaceAll(r'\', r'\\').replaceAll("'", r"\'");
      for (final route in const ['tasks', 'memories', 'folders', 'conversations']) {
        await _controller.runJavaScript("console.log('AUTODRIVE route-open $route=' + window.__ad.openTab('$route'));");
        await Future<void>.delayed(const Duration(milliseconds: 700));
        if (seedText.isNotEmpty && route != 'conversations') {
          await _controller.runJavaScript(
            "console.log('AUTODRIVE seed $route ' + window.__ad.seed('$route', '$seedText'));",
          );
          await Future<void>.delayed(const Duration(milliseconds: 1200));
        }
        await _controller.runJavaScript(
          "console.log('AUTODRIVE state $route rows=' + window.__ad.rows('$route')"
          " + ' pending=' + ((document.querySelector('.badge.pending') || {}).textContent || '0').trim()"
          " + ' createForm=' + !!document.querySelector('[data-action=\"create\"], form.add-row'));",
        );
      }
      // Must await between route switches: a click renders the next list on a
      // later frame, so synchronous reads would look like data loss.
      await _controller.runJavaScript(r'''
        (async function () {
          var routes = ['tasks', 'memories', 'conversations', 'folders'];
          var out = [];
          for (var i = 0; i < routes.length; i++) {
            window.__ad.openTab(routes[i]);
            await new Promise(function (r) { setTimeout(r, 500); });
            out.push(routes[i] + '=' + window.__ad.rows(routes[i]));
          }
          console.log('AUTODRIVE SUMMARY ' + out.join(' '));
        })();
      ''');
      await Future<void>.delayed(const Duration(milliseconds: 3200));
      if (_http != null) await _autodriveBridgeProbes();
      await _scheme?.log('AUTODRIVE-DONE addTask=${_addTask.isEmpty ? "(none)" : _addTask}');
      await _scheme?.drainSchemeLog();
      await _emitAcceptance('autodrive');
      return;
    }
    await _controller.runJavaScript("document.getElementById('btn-device').click()");
    await Future<void>.delayed(const Duration(milliseconds: 400));
    await _controller.runJavaScript("document.getElementById('btn-listen').click()");
    await Future<void>.delayed(const Duration(milliseconds: 800));
    await _controller.runJavaScript("document.getElementById('btn-bench').click()");
    await _emitAcceptance('autodrive');
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _transcriptTimer?.cancel();
    _acceptanceFallback?.cancel();
    super.dispose();
  }

  // ---------------------------------------------------------- bridge handler
  // Fake shell-side state; in the real app these read the BLE/capture layer.
  @override
  Future<DeviceState> getDeviceState() async {
    return const DeviceState(connected: true, deviceId: 'omi-proto-0001', batteryPct: 57);
  }

  @override
  Future<ListenSession> startListening(StartListeningParams params) async {
    final id = 'sess-${++_sessions}-${params.sampleRateHz}';
    _transcriptTimer?.cancel();
    var i = 0;
    const words = ['hey', 'so', 'the', 'bridge', 'round', 'trip', 'looks', 'fine'];
    _transcriptTimer = Timer.periodic(const Duration(milliseconds: 700), (t) {
      if (i >= words.length) {
        t.cancel();
        return;
      }
      _bridge.transcriptEvent(
        TranscriptEvent(
          sessionId: id,
          text: words.sublist(0, i + 1).join(' '),
          isFinal: i == words.length - 1,
          shellSentAtMs: DateTime.now().millisecondsSinceEpoch,
        ),
      );
      i++;
    });
    return ListenSession(sessionId: id);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0B0B0F),
      // Shell-level inset ownership: SafeArea keeps the WKWebView out of the
      // status bar and home indicator. The removed diagnostic strip previously
      // occupied that layout space; without it the shell must claim MediaQuery
      // padding here. Do not push iOS-only CSS padding into the shared surface.
      body: SafeArea(
        child: Stack(
          children: [
            WebViewWidget(controller: _controller),
            // Contract-gate error surface: shown when a bundle was refused
            // before navigation (the webview behind it keeps the last good
            // bundle — rollback is "do nothing").
            if (_blocked != null)
              Container(
                color: const Color(0xE61C0B0B),
                alignment: Alignment.center,
                padding: const EdgeInsets.all(24),
                child: Text(
                  'UPDATE BLOCKED\n\n$_blocked',
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 14, color: Color(0xFFFF453A)),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
