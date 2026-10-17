import 'package:flutter/material.dart';

import '../art.dart';
import '../theme.dart';
import '../widgets.dart';

/// 08 — Name.
class NameScreen extends StatefulWidget {
  const NameScreen({super.key, required this.onContinue});

  final ValueChanged<String> onContinue;

  @override
  State<NameScreen> createState() => _NameScreenState();
}

class _NameScreenState extends State<NameScreen> {
  final TextEditingController _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final name = _controller.text.trim();
    return DfPage(
      children: <Widget>[
        const DfProgress(step: 2),
        const DfHeadline("What's your name?"),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          decoration: BoxDecoration(color: t.surface, borderRadius: BorderRadius.circular(14)),
          child: TextField(
            controller: _controller,
            autofocus: true,
            cursorColor: t.accent,
            textCapitalization: TextCapitalization.words,
            style: t.label(size: 20),
            onChanged: (_) => setState(() {}),
            onSubmitted: (value) {
              if (value.trim().isNotEmpty) widget.onContinue(value.trim());
            },
            decoration: InputDecoration(
              border: InputBorder.none,
              hintText: 'Your name',
              hintStyle: t.label(size: 20, color: t.textTertiary),
            ),
          ),
        ),
        const Spacer(),
        DfButton('Continue', onPressed: name.isEmpty ? null : () => widget.onContinue(name)),
      ],
    );
  }
}

/// 09 — Primary language.
class LanguageScreen extends StatefulWidget {
  const LanguageScreen({super.key, required this.onContinue});

  final ValueChanged<String> onContinue;

  @override
  State<LanguageScreen> createState() => _LanguageScreenState();
}

class _LanguageScreenState extends State<LanguageScreen> {
  static const List<String> _languages = <String>['English', 'Español', 'Français', 'Deutsch', 'Português', 'Italiano'];

  String _selected = _languages.first;
  String _query = '';

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final visible = _languages.where((l) => l.toLowerCase().contains(_query.toLowerCase())).toList();
    return DfPage(
      children: <Widget>[
        const DfProgress(step: 3),
        const DfHeadline("What's your primary language?"),
        const DfBody('Omi uses it for transcription, summaries, and memories.'),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 14),
          decoration: BoxDecoration(color: t.surface, borderRadius: BorderRadius.circular(12)),
          child: TextField(
            cursorColor: t.accent,
            style: t.label(size: 16),
            onChanged: (value) => setState(() => _query = value),
            decoration: InputDecoration(
              border: InputBorder.none,
              icon: Icon(Icons.search, size: 18, color: t.textTertiary),
              hintText: 'Search',
              hintStyle: t.label(size: 16, color: t.textTertiary),
            ),
          ),
        ),
        DfCard(
          child: Column(
            children: <Widget>[
              for (final language in visible)
                DfListRow(
                  label: language,
                  emphasize: language == _selected,
                  trailing: language == _selected ? Icon(Icons.check, size: 18, color: t.accent) : null,
                  onTap: () => setState(() => _selected = language),
                ),
            ],
          ),
        ),
        const Spacer(),
        DfButton('Continue', onPressed: () => widget.onContinue(_selected)),
      ],
    );
  }
}

/// 10 — Background permissions. Bluetooth was already granted while pairing.
class PermissionsScreen extends StatefulWidget {
  const PermissionsScreen({super.key, required this.onContinue});

  final VoidCallback onContinue;

  @override
  State<PermissionsScreen> createState() => _PermissionsScreenState();
}

class _PermissionsScreenState extends State<PermissionsScreen> {
  static const List<(IconData, String, String)> _items = <(IconData, String, String)>[
    (Icons.bolt_outlined, 'Background activity', 'Keeps your Omi connected when the screen is off.'),
    (Icons.location_on_outlined, 'Location', 'Notes where conversations happened.'),
    (Icons.notifications_none, 'Notifications', 'Summaries, reminders and replies.'),
  ];

  final Set<String> _granted = <String>{'Background activity', 'Location', 'Notifications'};

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return DfPage(
      children: <Widget>[
        const DfProgress(step: 4),
        const DfHeadline('Let Omi work in the background'),
        DfCard(
          child: Column(
            children: <Widget>[
              for (final (icon, title, detail) in _items)
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                  child: Row(
                    children: <Widget>[
                      Icon(icon, size: 22, color: t.text),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: <Widget>[
                            Text(title, style: t.label(size: 16, weight: FontWeight.w600)),
                            const SizedBox(height: 2),
                            Text(detail, style: t.body(size: 13, color: t.textTertiary)),
                          ],
                        ),
                      ),
                      const SizedBox(width: 8),
                      DfToggle(
                        value: _granted.contains(title),
                        onChanged: (on) => setState(() => on ? _granted.add(title) : _granted.remove(title)),
                      ),
                    ],
                  ),
                ),
            ],
          ),
        ),
        const Spacer(),
        const DfCaption('Change these anytime in Settings.'),
        DfButton('Continue', onPressed: widget.onContinue),
      ],
    );
  }
}

/// 11 — Voice introduction. Prompts from `speech_profile_widget.dart`.
class VoiceIntroScreen extends StatefulWidget {
  const VoiceIntroScreen({super.key, required this.onDone});

  final VoidCallback onDone;

  @override
  State<VoiceIntroScreen> createState() => _VoiceIntroScreenState();
}

class _VoiceIntroScreenState extends State<VoiceIntroScreen> {
  static const List<String> _prompts = <String>[
    'My name is ___, and I spend most of my time ___.',
    'Right now, I am working on ___.',
    'Something I would like help remembering is ___.',
    'Right now my number one goal is to ___.',
  ];

  int _index = 0;
  bool _listening = false;

  void _advance() {
    if (_index == _prompts.length - 1) {
      widget.onDone();
      return;
    }
    setState(() {
      _index++;
      _listening = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final last = _index == _prompts.length - 1;
    return DfPage(
      children: <Widget>[
        const DfProgress(step: 5),
        const DfHeadline('Let Omi get to know you'),
        const DfBody("Finish four short sentences out loud. Speak toward your Omi — it's learning your voice."),
        Center(child: _VoiceOrb(listening: _listening)),
        DfCard(
          padding: const EdgeInsets.all(18),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Text('${_index + 1} of ${_prompts.length}', style: t.label(size: 12, color: t.textTertiary)),
              const SizedBox(height: 8),
              Text(_prompts[_index], style: t.headline(20).copyWith(height: 1.3)),
            ],
          ),
        ),
        const Spacer(),
        DfButton(
          _listening ? (last ? 'Finish' : 'Next') : 'Start Speaking',
          onPressed: _listening ? _advance : () => setState(() => _listening = true),
        ),
        DfButton('Skip Question', onPressed: _advance, kind: DfButtonKind.text),
      ],
    );
  }
}

class _VoiceOrb extends StatelessWidget {
  const _VoiceOrb({required this.listening});

  final bool listening;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    final dot = listening ? 64.0 : 56.0;
    return Container(
      width: 150,
      height: 150,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        border: Border.all(color: t.border),
      ),
      alignment: Alignment.center,
      child: Container(
        width: 100,
        height: 100,
        decoration: BoxDecoration(
          shape: BoxShape.circle,
          border: Border.all(color: t.textTertiary),
        ),
        alignment: Alignment.center,
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 250),
          width: dot,
          height: dot,
          decoration: BoxDecoration(shape: BoxShape.circle, gradient: t.accentGradient),
          child: Icon(listening ? Icons.graphic_eq : Icons.mic_none, color: t.onAccent),
        ),
      ),
    );
  }
}

/// 12 — Setting up. The rating prompt from today's setup page is replaced
/// with social proof: asking for a rating before anything has been recorded
/// wastes the prompt.
class SetupScreen extends StatefulWidget {
  const SetupScreen({super.key, required this.name, required this.onSeePlan});

  final String name;
  final VoidCallback onSeePlan;

  @override
  State<SetupScreen> createState() => _SetupScreenState();
}

class _SetupScreenState extends State<SetupScreen> with SingleTickerProviderStateMixin {
  static const List<String> _steps = <String>[
    'Omi paired',
    'Tuning transcription to your language',
    'Saving your voice profile',
    'Personalizing for your goal',
  ];

  late final AnimationController _controller = AnimationController(
    vsync: this,
    duration: const Duration(milliseconds: 2400),
  )..forward();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        final progress = _controller.value;
        final done = _controller.isCompleted;
        return DfPage(
          children: <Widget>[
            const DfEyebrow('Nearly there'),
            DfHeadline('Setting up your Omi, ${widget.name}'),
            Center(child: DfProgressRing(value: progress)),
            for (var i = 0; i < _steps.length; i++)
              _SetupStep(label: _steps[i], done: progress >= (i + 1) / _steps.length * 0.98),
            const Spacer(),
            DfCard(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Row(
                    children: <Widget>[for (var i = 0; i < 5; i++) Icon(Icons.star_rounded, size: 16, color: t.text)],
                  ),
                  const SizedBox(height: 6),
                  // Placeholder: swap in a real App Store review.
                  Text("“I haven't missed a follow-up since I started wearing it.”", style: t.label(size: 14)),
                  const SizedBox(height: 4),
                  Text('Trusted by 300,000+ professionals', style: t.body(size: 12, color: t.textTertiary)),
                ],
              ),
            ),
            DfButton('See my plan', onPressed: done ? widget.onSeePlan : null),
          ],
        );
      },
    );
  }
}

class _SetupStep extends StatelessWidget {
  const _SetupStep({required this.label, required this.done});

  final String label;
  final bool done;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return Row(
      children: <Widget>[
        Icon(
          done ? Icons.check_circle : Icons.radio_button_unchecked,
          size: 18,
          color: done ? t.success : t.textTertiary,
        ),
        const SizedBox(width: 10),
        Expanded(
          child: Text(
            label,
            style: t.label(weight: done ? FontWeight.w500 : FontWeight.w400, color: done ? t.text : t.textTertiary),
          ),
        ),
      ],
    );
  }
}

/// 13 — Your Omi is ready: plays back what onboarding captured.
class ReadyScreen extends StatelessWidget {
  const ReadyScreen({super.key, required this.name, required this.language, required this.onContinue});

  final String name;
  final String language;
  final VoidCallback onContinue;

  @override
  Widget build(BuildContext context) {
    final t = DfThemeScope.of(context);
    return DfPage(
      children: <Widget>[
        DfHeadline('Your Omi is ready, $name'),
        const DfBody("Here's what it knows so far."),
        DfCard(
          child: Column(
            children: <Widget>[
              const DfListRow(icon: Icons.bluetooth, label: 'Omi', value: 'Paired · 82%'),
              DfListRow(icon: Icons.language, label: 'Language', value: language),
              const DfListRow(icon: Icons.mic_none, label: 'Voice', value: 'Saved'),
              const DfListRow(icon: Icons.flag_outlined, label: 'Your goal', value: 'Saved'),
            ],
          ),
        ),
        const DfEyebrow('What Omi will do'),
        for (final item in const <String>[
          'Transcribe every call and meeting, live',
          'Pull out follow-ups before they slip',
          'Answer "what did they say about…?" later',
        ])
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: <Widget>[
              Icon(Icons.check, size: 18, color: t.success),
              const SizedBox(width: 10),
              Expanded(child: Text(item, style: t.label())),
            ],
          ),
        const Spacer(),
        DfButton('Continue', onPressed: onContinue),
      ],
    );
  }
}
