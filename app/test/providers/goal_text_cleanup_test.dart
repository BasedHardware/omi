import 'package:flutter_test/flutter_test.dart';
import 'package:omi/pages/onboarding/goal_text_cleanup.dart';

void main() {
  final cases = {
    'Right now my number one goal is to ship Omi this month.': 'Ship Omi this month',
    'Um, right now, my number one goal is to get 10 customers by Friday.': 'Get 10 customers by Friday',
    'My goal is not to work on weekends.': 'Not to work on weekends',
    'My primary goal is to not miss my medication.': 'Not miss my medication',
    "I don't want to take another job.": "I don't want to take another job",
    'My goal is to quit smoking, not just smoke less.': 'Quit smoking, not just smoke less',
    'So much depends on finishing this.': 'So much depends on finishing this',
    'I would like to run 5 km in under 30 minutes.': 'Run 5 km in under 30 minutes',
    'My goal is to launch iOS support.': 'Launch iOS support',
    'iOS accessibility': 'iOS accessibility',
    'Work in the U.S.': 'Work in the U.S.',
    'Finish the\n project   this week.': 'Finish the project this week',
    '“My goal is to learn French.”': 'Learn French',
    'Right now my number one goal is to.': '',
    'Mi objetivo es aprender francés.': 'Mi objetivo es aprender francés',
  };
  for (final entry in cases.entries) {
    test('preserves the outcome: ${entry.key}', () {
      expect(cleanIntroductionGoal(entry.key), entry.value);
    });
  }
}
