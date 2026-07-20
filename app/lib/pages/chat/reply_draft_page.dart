import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/reply_draft.dart';
import 'package:omi/providers/reply_draft_provider.dart';

class ReplyDraftPage extends StatefulWidget {
  const ReplyDraftPage({super.key});

  @override
  State<ReplyDraftPage> createState() => _ReplyDraftPageState();
}

class _ReplyDraftPageState extends State<ReplyDraftPage> {
  final _incomingController = TextEditingController();
  final _recipientController = TextEditingController();
  final _relationshipController = TextEditingController();
  final _goalController = TextEditingController();
  final _extraController = TextEditingController();

  String _tone = 'natural';
  String _length = 'medium';
  bool _includeMemories = true;
  bool _includeRecentChat = true;

  static const _tones = ['natural', 'warm', 'brief', 'professional', 'playful'];
  static const _lengths = ['short', 'medium', 'long'];

  @override
  void dispose() {
    _incomingController.dispose();
    _recipientController.dispose();
    _relationshipController.dispose();
    _goalController.dispose();
    _extraController.dispose();
    super.dispose();
  }

  ReplyDraftRequest _request() {
    return ReplyDraftRequest(
      incomingMessage: _incomingController.text.trim(),
      recipientName: _recipientController.text.trim(),
      channel: 'message',
      relationship: _relationshipController.text.trim(),
      goal: _goalController.text.trim(),
      extraContext: _extraController.text.trim(),
      tone: _tone,
      length: _length,
      includeMemories: _includeMemories,
      includeRecentChat: _includeRecentChat,
    );
  }

  Future<void> _generate() async {
    HapticFeedback.mediumImpact();
    await context.read<ReplyDraftProvider>().generate(_request());
  }

  Future<void> _copy(String text) async {
    await Clipboard.setData(ClipboardData(text: text));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Copied'),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        elevation: 0,
        title: const Text('Draft reply', style: TextStyle(color: Colors.white)),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back_ios_new, color: Colors.white),
          onPressed: () => Navigator.of(context).pop(),
        ),
      ),
      body: Consumer<ReplyDraftProvider>(
        builder: (context, provider, child) {
          return ListView(
            padding: const EdgeInsets.fromLTRB(18, 8, 18, 28),
            children: [
              _Section(
                title: 'Message to answer',
                child: _Input(
                  controller: _incomingController,
                  hint: 'Paste the text, DM, email, or comment here',
                  maxLines: 6,
                ),
              ),
              const SizedBox(height: 16),
              _Section(
                title: 'Context',
                child: Column(
                  children: [
                    _Input(
                      controller: _recipientController,
                      hint: 'Recipient name',
                    ),
                    const SizedBox(height: 10),
                    _Input(
                      controller: _relationshipController,
                      hint: 'Relationship or situation',
                    ),
                    const SizedBox(height: 10),
                    _Input(
                      controller: _goalController,
                      hint: 'What do you want this reply to do?',
                    ),
                    const SizedBox(height: 10),
                    _Input(
                      controller: _extraController,
                      hint: 'Anything else Omi should know',
                      maxLines: 3,
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              _Section(
                title: 'Tone',
                child: _ChipRow(
                  values: _tones,
                  selected: _tone,
                  onSelected: _setTone,
                ),
              ),
              const SizedBox(height: 16),
              _Section(
                title: 'Length',
                child: _ChipRow(
                  values: _lengths,
                  selected: _length,
                  onSelected: _setLength,
                ),
              ),
              const SizedBox(height: 16),
              _SwitchTile(
                title: 'Use my memories',
                subtitle: 'Pulls in relevant facts, preferences, and context.',
                value: _includeMemories,
                onChanged: (value) => setState(() => _includeMemories = value),
              ),
              const SizedBox(height: 10),
              _SwitchTile(
                title: 'Match my chat style',
                subtitle: 'Uses recent messages to keep the draft sounding like you.',
                value: _includeRecentChat,
                onChanged: (value) => setState(() => _includeRecentChat = value),
              ),
              const SizedBox(height: 18),
              ElevatedButton.icon(
                onPressed: provider.isLoading ? null : _generate,
                icon: provider.isLoading
                    ? const SizedBox(
                        width: 18,
                        height: 18,
                        child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.black,
                        ),
                      )
                    : const Icon(Icons.auto_fix_high_rounded),
                label: Text(
                  provider.draft == null ? 'Draft reply' : 'Regenerate',
                ),
                style: ElevatedButton.styleFrom(
                  foregroundColor: Colors.black,
                  backgroundColor: Colors.white,
                  disabledBackgroundColor: Colors.white.withValues(alpha: 0.55),
                  padding: const EdgeInsets.symmetric(vertical: 14),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
              ),
              if (provider.error != null) ...[
                const SizedBox(height: 14),
                Text(
                  provider.error!,
                  style: const TextStyle(
                    color: Color(0xFFFF8A80),
                    fontSize: 14,
                  ),
                ),
              ],
              if (provider.draft != null) ...[
                const SizedBox(height: 22),
                _DraftResult(draft: provider.draft!, onCopy: _copy),
              ],
            ],
          );
        },
      ),
    );
  }

  void _setTone(String tone) => setState(() => _tone = tone);

  void _setLength(String length) => setState(() => _length = length);
}

class _Section extends StatelessWidget {
  const _Section({required this.title, required this.child});

  final String title;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.only(left: 2, bottom: 8),
          child: Text(
            title,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 15,
              fontWeight: FontWeight.w600,
            ),
          ),
        ),
        child,
      ],
    );
  }
}

class _Input extends StatelessWidget {
  const _Input({
    required this.controller,
    required this.hint,
    this.maxLines = 1,
  });

  final TextEditingController controller;
  final String hint;
  final int maxLines;

  @override
  Widget build(BuildContext context) {
    return TextField(
      controller: controller,
      maxLines: maxLines,
      minLines: 1,
      keyboardType: TextInputType.multiline,
      textCapitalization: TextCapitalization.sentences,
      style: const TextStyle(color: Colors.white, fontSize: 15, height: 1.35),
      decoration: InputDecoration(
        hintText: hint,
        hintStyle: TextStyle(
          color: Colors.white.withValues(alpha: 0.42),
          fontSize: 15,
        ),
        filled: true,
        fillColor: const Color(0xFF1F1F25),
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 14,
          vertical: 13,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Color(0xFF34343B)),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(12),
          borderSide: const BorderSide(color: Colors.white),
        ),
      ),
    );
  }
}

class _ChipRow extends StatelessWidget {
  const _ChipRow({
    required this.values,
    required this.selected,
    required this.onSelected,
  });

  final List<String> values;
  final String selected;
  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) {
    return Wrap(
      spacing: 8,
      runSpacing: 8,
      children: values.map((value) {
        final isSelected = value == selected;
        return ChoiceChip(
          label: Text(value[0].toUpperCase() + value.substring(1)),
          selected: isSelected,
          onSelected: (_) => onSelected(value),
          selectedColor: const Color(0xFF34343B),
          backgroundColor: const Color(0xFF1F1F25),
          labelStyle: TextStyle(
            color: isSelected ? Colors.white : Colors.white.withValues(alpha: 0.72),
            fontSize: 13,
          ),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(10),
            side: BorderSide(
              color: isSelected ? Colors.white : const Color(0xFF34343B),
            ),
          ),
        );
      }).toList(),
    );
  }
}

class _SwitchTile extends StatelessWidget {
  const _SwitchTile({
    required this.title,
    required this.subtitle,
    required this.value,
    required this.onChanged,
  });

  final String title;
  final String subtitle;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 12, 10, 12),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF34343B)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 3),
                Text(
                  subtitle,
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.55),
                    fontSize: 12,
                    height: 1.25,
                  ),
                ),
              ],
            ),
          ),
          Switch(
            value: value,
            activeThumbColor: Colors.white,
            onChanged: onChanged,
          ),
        ],
      ),
    );
  }
}

class _DraftResult extends StatelessWidget {
  const _DraftResult({required this.draft, required this.onCopy});

  final ReplyDraftResponse draft;
  final ValueChanged<String> onCopy;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _DraftCard(title: 'Draft', text: draft.draft, onCopy: onCopy),
        if (draft.alternatives.isNotEmpty) ...[
          const SizedBox(height: 14),
          const Text(
            'Alternatives',
            style: TextStyle(
              color: Colors.white,
              fontSize: 15,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          for (final alternative in draft.alternatives) ...[
            _DraftCard(
              title: 'Option',
              text: alternative,
              onCopy: onCopy,
              compact: true,
            ),
            const SizedBox(height: 10),
          ],
        ],
        if (draft.safetyNotes.isNotEmpty) ...[
          const SizedBox(height: 6),
          Text(
            draft.safetyNotes.join(' '),
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.55),
              fontSize: 12,
              height: 1.35,
            ),
          ),
        ],
        const SizedBox(height: 8),
        Text(
          'Review before sending. Omi drafted this, but you decide what leaves your phone.',
          style: TextStyle(
            color: Colors.white.withValues(alpha: 0.50),
            fontSize: 12,
            height: 1.35,
          ),
        ),
      ],
    );
  }
}

class _DraftCard extends StatelessWidget {
  const _DraftCard({
    required this.title,
    required this.text,
    required this.onCopy,
    this.compact = false,
  });

  final String title;
  final String text;
  final ValueChanged<String> onCopy;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.fromLTRB(
        14,
        compact ? 12 : 14,
        10,
        compact ? 12 : 14,
      ),
      decoration: BoxDecoration(
        color: const Color(0xFF1F1F25),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF34343B)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  title,
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.62),
                    fontSize: 12,
                  ),
                ),
              ),
              IconButton(
                tooltip: 'Copy',
                onPressed: () => onCopy(text),
                icon: const Icon(
                  Icons.copy_rounded,
                  color: Colors.white,
                  size: 18,
                ),
                visualDensity: VisualDensity.compact,
              ),
            ],
          ),
          Text(
            text,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 15,
              height: 1.42,
            ),
          ),
        ],
      ),
    );
  }
}
