import 'package:flutter_test/flutter_test.dart';

import 'package:omi/pages/conversations/widgets/goals_widget.dart';

void main() {
  test('large goal targets do not create unbounded slider divisions', () {
    expect(goalSliderDivisions(1000000000), isNull);
    expect(goalSliderDivisions(double.infinity), isNull);
  });

  test('small integral goals retain one-step slider divisions', () {
    expect(goalSliderDivisions(1), 1);
    expect(goalSliderDivisions(20), 20);
    expect(goalSliderDivisions(100), 100);
  });

  test('fractional and invalid targets use a continuous slider', () {
    expect(goalSliderDivisions(2.5), isNull);
    expect(goalSliderDivisions(0), isNull);
    expect(goalSliderDivisions(-1), isNull);
  });
}
