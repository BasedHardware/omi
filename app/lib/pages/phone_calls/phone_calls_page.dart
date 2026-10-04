import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_contacts/flutter_contacts.dart';
// hide PermissionStatus: flutter_contacts has its own PermissionStatus enum, and this
// file never spells out permission_handler's version by name (only inferred via `var`).
import 'package:permission_handler/permission_handler.dart' hide PermissionStatus;
import 'package:intl_country_data/intl_country_data.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/pages/phone_calls/active_call_page.dart';
import 'package:omi/pages/phone_calls/phone_setup_intro_page.dart';
import 'package:omi/pages/settings/phone_call_settings_page.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/mobile/native_ui/native_phone_projection.dart';

class PhoneCallsPage extends StatefulWidget {
  const PhoneCallsPage({super.key});

  @override
  State<PhoneCallsPage> createState() => _PhoneCallsPageState();
}

class _PhoneCallsPageState extends State<PhoneCallsPage> with SingleTickerProviderStateMixin {
  late TabController _tabController;
  final TextEditingController _searchController = TextEditingController();
  final TextEditingController _dialpadController = TextEditingController();

  List<Contact> _contacts = [];
  List<Contact> _filteredContacts = [];
  bool _loadingContacts = true;
  bool _permissionDenied = false;

  @override
  void initState() {
    super.initState();
    _tabController = TabController(length: 2, vsync: this);
    _tabController.addListener(_tabChanged);
    _loadContacts();
    PlatformManager.instance.analytics.phoneCallPageOpened();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<PhoneCallProvider>().loadVerifiedNumbers();
    });
  }

  @override
  void dispose() {
    _tabController.removeListener(_tabChanged);
    _tabController.dispose();
    _searchController.dispose();
    _dialpadController.dispose();
    super.dispose();
  }

  void _tabChanged() {
    if (mounted) setState(() {});
  }

  Future<void> _loadContacts() async {
    try {
      final status = await FlutterContacts.permissions.request(PermissionType.read);
      if (!mounted) return;
      if (status != PermissionStatus.granted && status != PermissionStatus.limited) {
        setState(() {
          _permissionDenied = true;
          _loadingContacts = false;
        });
        return;
      }

      var contacts = await FlutterContacts.getAll(properties: {ContactProperty.phone});
      contacts = contacts.where((c) => c.phones.isNotEmpty).toList();
      contacts.sort((a, b) => (a.displayName ?? '').compareTo(b.displayName ?? ''));

      if (mounted) {
        setState(() {
          _contacts = contacts;
          _filteredContacts = contacts;
          _loadingContacts = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _loadingContacts = false;
        });
      }
    }
  }

  void _filterContacts(String query) {
    if (!mounted) return;
    setState(() {
      if (query.isEmpty) {
        _filteredContacts = _contacts;
      } else {
        _filteredContacts = _contacts.where((c) {
          return (c.displayName ?? '').toLowerCase().contains(query.toLowerCase()) ||
              c.phones.any((p) => p.number.contains(query));
        }).toList();
      }
    });
  }

  Future<void> _makeCall(String phoneNumber, {String? contactName}) async {
    // Strip spaces, dashes, parens, dots — contacts often have formatted numbers
    phoneNumber = phoneNumber.replaceAll(RegExp(r'[\s\-\(\).]+'), '');

    var provider = context.read<PhoneCallProvider>();

    // Block if already on a call
    if (provider.callState != PhoneCallState.idle && provider.callState != PhoneCallState.ended) {
      if (!mounted) return;
      OmiFeedback.info(context, context.l10n.callAlreadyInProgress);
      return;
    }

    if (provider.verifiedNumbers.isEmpty) {
      routeToPage(context, const PhoneSetupIntroPage());
      return;
    }

    // If the number doesn't start with '+', prepend the country code from the user's verified number
    if (!phoneNumber.startsWith('+')) {
      var verified = provider.verifiedNumbers.first.phoneNumber;
      var countryCode = _extractCountryCode(verified);
      if (countryCode != null) {
        phoneNumber = '$countryCode$phoneNumber';
      }
    }

    var success = await provider.startCall(phoneNumber);
    if (!mounted) return;

    if (success) {
      routeToPage(context, const ActiveCallPage());
    } else {
      final dialed = phoneNumber;
      OmiFeedback.error(
        context,
        provider.error ?? context.l10n.failedToStartCall,
        actionLabel: context.l10n.tryAgain,
        onAction: () => _makeCall(dialed, contactName: contactName),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<PhoneCallProvider>(
      builder: (context, provider, _) {
        if (!provider.numbersLoaded) {
          return IosNativeSurface(
              title: context.l10n.phonePageTitle,
              sections: const [],
              loading: true,
              toolbar: [
                NativeRow('phone_back', context.l10n.back,
                    symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop())
              ],
              fallback: Scaffold(appBar: AppBar(leading: const OmiBackButton()), body: const OmiLoadingState()));
        }
        if (provider.verifiedNumbers.isEmpty) {
          return const PhoneSetupIntroPage();
        }
        return _buildMainPage(context);
      },
    );
  }

  Widget _buildMainPage(BuildContext context) {
    final classic = Scaffold(
      appBar: AppBar(
        leading: const OmiBackButton(),
        title: Text(context.l10n.phonePageTitle),
        actions: [
          OmiIconButton(
            icon: const Icon(Icons.settings_outlined),
            label: context.l10n.settings,
            onPressed: () => routeToPage(context, const PhoneCallSettingsPage()),
          ),
        ],
        bottom: TabBar(
          controller: _tabController,
          indicatorColor: OmiColors.accent,
          indicatorWeight: 3,
          labelColor: OmiColors.textPrimary,
          labelStyle: const TextStyle(fontWeight: FontWeight.w600),
          unselectedLabelColor: OmiColors.textTertiary,
          tabs: [
            Tab(text: context.l10n.phoneContactsTab),
            Tab(text: context.l10n.phoneKeypadTab),
          ],
        ),
      ),
      body: Column(
        children: [
          const _FreeQuotaBanner(),
          Expanded(
            child: TabBarView(controller: _tabController, children: [_buildContactsTab(), _buildKeypadTab()]),
          ),
        ],
      ),
    );
    return Consumer<UsageProvider>(builder: (context, usage, _) {
      final quota = _phoneQuotaText(context, usage);
      return IosNativeSurface(
        title: context.l10n.phonePageTitle,
        loading: _tabController.index == 0 && _loadingContacts,
        search: _tabController.index == 0 && !_permissionDenied && !_loadingContacts
            ? (value) {
                _searchController.text = value as String;
                _filterContacts(value);
              }
            : null,
        searchValue: _searchController.text,
        searchPlaceholder: context.l10n.searchContacts,
        toolbar: [
          NativeRow('phone_back', context.l10n.back,
              symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
          NativeRow('phone_settings', context.l10n.settings,
              symbol: 'gearshape', action: (_) => routeToPage(context, const PhoneCallSettingsPage())),
        ],
        sections: [
          NativeSection('phone_tabs', [
            NativeRow('phone_tab', context.l10n.phonePageTitle,
                kind: 'segmented',
                value: _tabController.index.toString(),
                options: {'0': context.l10n.phoneContactsTab, '1': context.l10n.phoneKeypadTab},
                action: (value) => _tabController.animateTo(int.parse(value as String))),
            if (quota != null) NativeRow('phone_quota', quota, kind: 'label'),
          ]),
          if (_tabController.index == 0)
            NativeSection('phone_contacts', [
              if (_permissionDenied) ...[
                NativeRow('phone_permission_reason', context.l10n.phoneContactsAccessTitle,
                    subtitle: context.l10n.grantContactsAccess, kind: 'label'),
                NativeRow('phone_permission_allow', context.l10n.phoneAllow, action: (_) => _allowContacts()),
              ] else if (!_loadingContacts) ...[
                if (_filteredContacts.isEmpty)
                  NativeRow('phone_contacts_empty', context.l10n.phoneNoContactsFound, kind: 'label'),
                for (final contact in _filteredContacts)
                  NativeRow('phone_contact_${contact.id}', contact.displayName ?? '',
                      subtitle: '${contact.phones.first.label.label.name} ${contact.phones.first.number}',
                      symbol: 'phone',
                      action: (_) => _makeCall(contact.phones.first.number, contactName: contact.displayName)),
              ],
            ]),
          if (_tabController.index == 1)
            NativeSection('phone_dialer', [
              nativePhoneKeypad(
                  id: 'phone_keypad',
                  title: context.l10n.phoneEnterNumber,
                  digits: _dialpadController.text,
                  dtmf: false,
                  eraseLabel: context.l10n.delete,
                  clearLabel: context.l10n.clearAll,
                  action: (value) {
                    HapticFeedback.lightImpact();
                    setState(() {
                      if (value == 'clear') {
                        _dialpadController.clear();
                      } else if (value == 'erase') {
                        if (_dialpadController.text.isNotEmpty) {
                          _dialpadController.text =
                              _dialpadController.text.substring(0, _dialpadController.text.length - 1);
                        }
                      } else {
                        _dialpadController.text += value as String;
                      }
                    });
                  }),
              NativeRow('phone_paste', context.l10n.paste, symbol: 'doc.on.clipboard', action: (_) => _nativePaste()),
              NativeRow('phone_call', context.l10n.phoneCallButton,
                  symbol: 'phone.fill', enabled: _dialpadController.text.isNotEmpty, action: (_) {
                HapticFeedback.mediumImpact();
                return _makeCall(_dialpadController.text);
              }),
            ]),
        ],
        fallback: classic,
      );
    });
  }

  Future<void> _allowContacts() async {
    final status = await Permission.contacts.status;
    if (status.isPermanentlyDenied || status.isDenied) {
      await openAppSettings();
    } else {
      await FlutterContacts.permissions.request(PermissionType.read);
    }
    if (mounted) await _loadContacts();
  }

  Future<void> _nativePaste() async {
    HapticFeedback.lightImpact();
    final data = await Clipboard.getData(Clipboard.kTextPlain);
    if (!mounted || data?.text == null) return;
    final number = _sanitizePastedNumber(data!.text!);
    if (number.isEmpty) return;
    await showOmiRowMenu(context, actions: [
      OmiMenuAction(
          icon: Icons.content_paste,
          label: context.l10n.paste,
          onSelected: () {
            if (mounted) {
              HapticFeedback.mediumImpact();
              setState(() => _dialpadController.text = number);
            }
          })
    ]);
  }

  Widget _buildContactsTab() {
    if (_permissionDenied) {
      return OmiEmptyState(
        icon: Icons.contacts_outlined,
        title: context.l10n.phoneContactsAccessTitle,
        message: context.l10n.grantContactsAccess,
        action: OmiButton(
          label: context.l10n.phoneAllow,
          size: OmiButtonSize.compact,
          onPressed: _allowContacts,
        ),
      );
    }

    if (_loadingContacts) {
      return const OmiLoadingState();
    }

    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.all(OmiSpacing.sm),
          child: OmiSearchField(
            placeholder: context.l10n.searchContacts,
            controller: _searchController,
            onChanged: _filterContacts,
          ),
        ),
        Expanded(
          child: _filteredContacts.isEmpty
              ? OmiEmptyState(icon: Icons.person_search_outlined, title: context.l10n.phoneNoContactsFound)
              : ListView.separated(
                  itemCount: _filteredContacts.length,
                  separatorBuilder: (_, __) => Divider(color: OmiColors.border, height: 1, indent: 72),
                  itemBuilder: (context, index) {
                    var contact = _filteredContacts[index];
                    var phone = contact.phones.first;
                    var name = contact.displayName ?? '';
                    return _ContactRow(
                      name: name,
                      phone: '${phone.label.label.name} ${phone.number}',
                      initial: name.isNotEmpty ? name[0].toUpperCase() : '?',
                      onCall: () => _makeCall(phone.number, contactName: name),
                    );
                  },
                ),
        ),
      ],
    );
  }

  Widget _buildKeypadTab() {
    var hasDigits = _dialpadController.text.isNotEmpty;
    return Column(
      children: [
        const Spacer(flex: 2),
        // Number display — sits right above the keypad
        Padding(
          padding: const EdgeInsets.symmetric(horizontal: 24),
          child: SizedBox(
            height: 56,
            child: Row(
              children: [
                // Invisible spacer to balance the backspace button
                const SizedBox(width: 48),
                Expanded(
                  child: GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onLongPressStart: (details) => _showPasteMenu(details.globalPosition),
                    child: Text(
                      hasDigits ? _dialpadController.text : context.l10n.phoneEnterNumber,
                      textAlign: TextAlign.center,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: hasDigits
                            ? (_dialpadController.text.length > 12
                                ? OmiType.title2.fontSize
                                : OmiType.largeTitle.fontSize)
                            : OmiType.title3.fontSize,
                        fontWeight: FontWeight.w300,
                        letterSpacing: hasDigits ? 2 : 0,
                        color: hasDigits ? OmiColors.textPrimary : OmiColors.textTertiary,
                      ),
                    ),
                  ),
                ),
                SizedBox(
                  width: 48,
                  child: hasDigits
                      ? Semantics(
                          button: true,
                          label: context.l10n.delete,
                          excludeSemantics: true,
                          child: GestureDetector(
                            behavior: HitTestBehavior.opaque,
                            onTap: () {
                              HapticFeedback.lightImpact();
                              setState(() {
                                _dialpadController.text = _dialpadController.text.substring(
                                  0,
                                  _dialpadController.text.length - 1,
                                );
                              });
                            },
                            onLongPress: () {
                              HapticFeedback.mediumImpact();
                              setState(() {
                                _dialpadController.text = '';
                              });
                            },
                            child: Center(
                              child: Icon(Icons.backspace_outlined, color: OmiColors.textSecondary, size: 22),
                            ),
                          ),
                        )
                      : null,
                ),
              ],
            ),
          ),
        ),
        const SizedBox(height: 16),
        // Keypad grid
        _buildDialpad(),
        const SizedBox(height: 20),
        // Call button
        // Green is state here (ready to dial), not decoration.
        Semantics(
          button: true,
          enabled: hasDigits,
          label: context.l10n.phoneCallButton,
          excludeSemantics: true,
          child: GestureDetector(
            onTap: hasDigits
                ? () {
                    HapticFeedback.mediumImpact();
                    _makeCall(_dialpadController.text);
                  }
                : null,
            child: AnimatedContainer(
              duration: OmiMotion.of(context).quick,
              width: 68,
              height: 68,
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: hasDigits ? OmiColors.success : OmiColors.surface1,
              ),
              child: Icon(Icons.phone, color: hasDigits ? OmiColors.textPrimary : OmiColors.textDisabled, size: 32),
            ),
          ),
        ),
        const Spacer(flex: 1),
        SizedBox(height: MediaQuery.of(context).viewPadding.bottom + 8),
      ],
    );
  }

  Widget _buildDialpad() {
    const keys = [
      ['1', '2', '3'],
      ['4', '5', '6'],
      ['7', '8', '9'],
      ['*', '0', '#'],
    ];
    const subtexts = [
      ['', 'ABC', 'DEF'],
      ['GHI', 'JKL', 'MNO'],
      ['PQRS', 'TUV', 'WXYZ'],
      ['', '+', ''],
    ];

    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 32),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: List.generate(keys.length, (row) {
          return Padding(
            padding: const EdgeInsets.symmetric(vertical: 4),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceEvenly,
              children: List.generate(keys[row].length, (col) {
                return _DialpadKey(
                  digit: keys[row][col],
                  subtext: subtexts[row][col],
                  onTap: () {
                    HapticFeedback.lightImpact();
                    setState(() {
                      _dialpadController.text += keys[row][col];
                    });
                  },
                  onLongPress: keys[row][col] == '0'
                      ? () {
                          HapticFeedback.mediumImpact();
                          setState(() {
                            _dialpadController.text += '+';
                          });
                        }
                      : null,
                );
              }),
            ),
          );
        }),
      ),
    );
  }

  /// Keep only dialpad-valid characters (digits, *, #) plus a leading +.
  /// Strips spaces, dashes, parens, dots, and other formatting from pasted text
  /// like "+1 (415) 555-1234" → "+14155551234".
  String _sanitizePastedNumber(String input) {
    final buf = StringBuffer();
    var seenPlus = false;
    for (var i = 0; i < input.length; i++) {
      final ch = input[i];
      if (ch == '+' && !seenPlus && buf.isEmpty) {
        buf.write('+');
        seenPlus = true;
      } else if (ch.codeUnitAt(0) >= 0x30 && ch.codeUnitAt(0) <= 0x39) {
        buf.write(ch);
      } else if (ch == '*' || ch == '#') {
        buf.write(ch);
      }
    }
    return buf.toString();
  }

  Future<void> _showPasteMenu(Offset globalPosition) async {
    HapticFeedback.lightImpact();
    final clipboardData = await Clipboard.getData(Clipboard.kTextPlain);
    if (!mounted) return;

    final raw = clipboardData?.text;
    if (raw == null || raw.trim().isEmpty) return;

    final sanitized = _sanitizePastedNumber(raw);
    if (sanitized.isEmpty) return;

    final overlay = Overlay.of(context).context.findRenderObject() as RenderBox?;
    if (overlay == null) return;

    final selected = await showMenu<String>(
      context: context,
      color: OmiColors.surface2,
      position: RelativeRect.fromLTRB(
        globalPosition.dx,
        globalPosition.dy,
        overlay.size.width - globalPosition.dx,
        overlay.size.height - globalPosition.dy,
      ),
      items: [
        PopupMenuItem<String>(
          value: 'paste',
          child: Text(context.l10n.paste, style: OmiType.body),
        ),
      ],
    );

    if (selected == 'paste' && mounted) {
      HapticFeedback.mediumImpact();
      setState(() {
        _dialpadController.text = sanitized;
      });
    }
  }

  /// Extracts the country code (e.g. "+1", "+91") from an E.164 phone number
  /// by matching against known country dial codes (longest match first).
  String? _extractCountryCode(String e164Number) {
    if (!e164Number.startsWith('+')) return null;
    var digits = e164Number.substring(1); // strip '+'
    var allCountries = IntlCountryData.all();
    // Try longest match first (country codes are 1-3 digits)
    for (var len = 3; len >= 1; len--) {
      if (digits.length <= len) continue;
      var candidate = digits.substring(0, len);
      if (allCountries.any((c) => c.telephoneCode == candidate)) {
        return '+$candidate';
      }
    }
    return null;
  }
}

class _ContactRow extends StatelessWidget {
  final String name;
  final String phone;
  final String initial;
  final VoidCallback onCall;

  const _ContactRow({required this.name, required this.phone, required this.initial, required this.onCall});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      hint: context.l10n.phoneCallButton,
      child: InkWell(
        onTap: onCall,
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
          child: Row(
            children: [
              ExcludeSemantics(
                child: CircleAvatar(
                  radius: 20,
                  backgroundColor: OmiColors.surface3,
                  child: Text(initial, style: OmiType.callout),
                ),
              ),
              const SizedBox(width: OmiSpacing.md),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(name, style: OmiType.callout),
                    const SizedBox(height: 2),
                    Text(phone, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
                  ],
                ),
              ),
              // The whole row dials; the glyph only says so.
              ExcludeSemantics(child: Icon(Icons.phone, color: OmiColors.textSecondary, size: 22)),
            ],
          ),
        ),
      ),
    );
  }
}

class _FreeQuotaBanner extends StatelessWidget {
  const _FreeQuotaBanner();

  @override
  Widget build(BuildContext context) {
    return Consumer<UsageProvider>(
      builder: (context, usage, _) {
        final text = _phoneQuotaText(context, usage);
        if (text == null) return const SizedBox.shrink();
        return Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 10),
          color: OmiColors.surface1,
          child: Row(
            children: [
              ExcludeSemantics(child: Icon(Icons.info_outline, size: 16, color: OmiColors.textTertiary)),
              const SizedBox(width: OmiSpacing.xs),
              Expanded(child: Text(text, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary))),
            ],
          ),
        );
      },
    );
  }
}

String? _phoneQuotaText(BuildContext context, UsageProvider usage) {
  final quota = usage.phoneCallQuota;
  if (quota == null || quota.isPaid) return null;
  final limit = quota.monthlyLimit;
  if (limit == null || limit <= 0) return null;
  final remaining = quota.remaining ?? (limit - quota.monthlyUsed);
  final maxMinutes = (quota.maxDurationSeconds ?? 0) ~/ 60;
  final l10n = context.l10n;
  if (remaining <= 0) return l10n.phoneFreeCallLimitReached;
  if (maxMinutes > 0) return l10n.phoneFreeCallsRemainingWithMax(remaining, limit, maxMinutes);
  return l10n.phoneFreeCallsRemaining(remaining, limit);
}

class _DialpadKey extends StatelessWidget {
  final String digit;
  final String subtext;
  final VoidCallback onTap;
  final VoidCallback? onLongPress;

  const _DialpadKey({required this.digit, required this.subtext, required this.onTap, this.onLongPress});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: digit,
      excludeSemantics: true,
      child: InkWell(
        onTap: onTap,
        onLongPress: onLongPress,
        customBorder: const CircleBorder(),
        splashColor: OmiColors.textPrimary.withValues(alpha: 0.08),
        highlightColor: OmiColors.textPrimary.withValues(alpha: 0.05),
        child: Container(
          width: 72,
          height: 72,
          decoration: BoxDecoration(shape: BoxShape.circle, color: OmiColors.surface1),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              Text(digit, style: OmiType.title1.copyWith(fontWeight: FontWeight.w300)),
              if (subtext.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 1),
                  child: Text(
                    subtext,
                    style: OmiType.caption.copyWith(
                      fontWeight: FontWeight.w500,
                      color: OmiColors.textTertiary,
                      letterSpacing: 1.5,
                    ),
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}
