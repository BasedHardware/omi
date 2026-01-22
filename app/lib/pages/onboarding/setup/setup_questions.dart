import 'package:flutter/material.dart';

import 'package:omi/pages/speech_profile/page.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';

class SetupQuestionsPage extends StatefulWidget {
  const SetupQuestionsPage({super.key});

  @override
  State<SetupQuestionsPage> createState() => _SetupQuestionsPageState();
}

class _SetupQuestionsPageState extends State<SetupQuestionsPage> {
  List<String> options3 = ['18-25', '25-35', '35-45', '45-60', '60+'];

  String? selectedProfession;
  String? selectedUsage;
  String? selectedAge;

  @override
  Widget build(BuildContext context) {
    final List<String> options = [
      context.l10n.professionEntrepreneur,
      context.l10n.professionSoftwareEngineer,
      context.l10n.professionProductManager,
      context.l10n.professionExecutive,
      context.l10n.professionSales,
      context.l10n.professionStudent,
    ];
    final List<String> options2 = [
      context.l10n.usageAtWork,
      context.l10n.usageIrlEvents,
      context.l10n.usageOnline,
      context.l10n.usageSocialSettings,
      context.l10n.usageEverywhere,
    ];
    return PopScope(
      canPop: true,
      child: Scaffold(
        backgroundColor: Theme.of(context).colorScheme.primary,
        body: ListView(
          children: [
            const SizedBox(height: 16),
            const SizedBox(height: 16),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Text(
                context.l10n.setupQuestionsIntro,
                style: Theme.of(context).textTheme.titleLarge,
                textAlign: TextAlign.start,
              ),
            ),
            const SizedBox(height: 40),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Text(context.l10n.setupQuestionProfession, style: Theme.of(context).textTheme.titleLarge),
            ),
            const SizedBox(height: 16),
            for (var option in options)
              RadioListTile<String>(
                title: Text(option, style: Theme.of(context).textTheme.titleMedium),
                groupValue: selectedProfession,
                value: option,
                onChanged: (value) => setState(() => selectedProfession = value),
              ),
            const SizedBox(height: 40),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Text(context.l10n.setupQuestionUsage, style: Theme.of(context).textTheme.titleLarge),
            ),
            const SizedBox(height: 16),
            for (var i = 0; i < options2.length; i++)
              RadioListTile<String>(
                title: Text(options2[i], style: Theme.of(context).textTheme.titleMedium),
                groupValue: selectedUsage,
                value: options2[i],
                onChanged: (value) => setState(() => selectedUsage = value),
              ),
            const SizedBox(height: 40),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Text(context.l10n.setupQuestionAge, style: Theme.of(context).textTheme.titleLarge),
            ),
            const SizedBox(height: 16),
            for (var option in options3)
              RadioListTile<String>(
                title: Text(option, style: Theme.of(context).textTheme.titleMedium),
                groupValue: selectedAge,
                value: option,
                onChanged: (value) => setState(() => selectedAge = value),
              ),
            const SizedBox(height: 40),
            Center(
              child: MaterialButton(
                onPressed: () {
                  if (selectedProfession != null && selectedUsage != null && selectedAge != null) {
                    MixpanelManager().setUserProperties(selectedProfession!, selectedUsage!, selectedAge!);
                    Navigator.of(context)
                        .pushReplacement(MaterialPageRoute(builder: (c) => const SpeechProfilePage(onbording: true)));
                  } else {
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(context.l10n.setupAnswerAllQuestions,
                          style: const TextStyle(color: Colors.white)),
                      duration: const Duration(seconds: 2),
                    ));
                  }
                },
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12), side: const BorderSide(color: Colors.grey)),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  child: Text(context.l10n.continueButton, style: Theme.of(context).textTheme.titleMedium),
                ),
              ),
            ),
            const SizedBox(height: 16),
            Center(
              child: GestureDetector(
                onTap: () {
                  Navigator.of(context)
                      .pushReplacement(MaterialPageRoute(builder: (c) => const SpeechProfilePage(onbording: true)));
                },
                child: Text(
                  context.l10n.setupSkipHelp,
                  style: const TextStyle(color: Colors.grey, decoration: TextDecoration.underline),
                ),
              ),
            )
          ],
        ),
      ),
    );
  }
}
