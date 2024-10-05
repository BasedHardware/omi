import 'package:flutter/material.dart';
import 'package:friend_private/pages/speech_profile/page.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';

class SetupQuestionsPage extends StatefulWidget {
  const SetupQuestionsPage({super.key});

  @override
  State<SetupQuestionsPage> createState() => _SetupQuestionsPageState();
}

class _SetupQuestionsPageState extends State<SetupQuestionsPage> {
  List<String> options = ['Entrepreneur', 'Software Engineer', 'Product Manager', 'Executive', 'Sales', 'Student'];
  List<String> options2 = ['At work', 'IRL Events', 'Online', 'In Social Settings', 'Everywhere'];
  List<String> options3 = ['18-25', '25-35', '35-45', '45-60', '60+'];

  String? selectedProfession;
  String? selectedUsage;
  String? selectedAge;

  @override
  Widget build(BuildContext context) {
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
                'Help us improve Omi by answering a few questions.  🫶 💜',
                style: Theme.of(context).textTheme.titleLarge,
                textAlign: TextAlign.start,
              ),
            ),
            const SizedBox(height: 40),
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Text('1. What do you do?', style: Theme.of(context).textTheme.titleLarge),
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
              child: Text('2. Where do you plan to use your Omi?', style: Theme.of(context).textTheme.titleLarge),
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
              child: Text('3. What\'s your age range?', style: Theme.of(context).textTheme.titleLarge),
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
                    ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
                      content: Text('You haven\'t answered all the questions yet! 🥺',
                          style: TextStyle(color: Colors.white)),
                      duration: Duration(seconds: 2),
                    ));
                  }
                },
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(12), side: const BorderSide(color: Colors.grey)),
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  child: Text('Continue', style: Theme.of(context).textTheme.titleMedium),
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
                child: const Text(
                  'Skip, I don\'t want to help :C',
                  style: TextStyle(color: Colors.grey, decoration: TextDecoration.underline),
                ),
              ),
            )
          ],
        ),
      ),
    );
  }
}
