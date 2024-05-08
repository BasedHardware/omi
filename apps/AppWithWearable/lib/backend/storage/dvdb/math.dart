import 'package:ml_linalg/linalg.dart';

class MathFunctions {
  MathFunctions._internal();

  static final MathFunctions _shared = MathFunctions._internal();

  factory MathFunctions() {
    return _shared;
  }

  double cosineSimilarity(List<double> a, List<double> b) {
    assert(a.length == b.length);

    Vector aVector = Vector.fromList(a);
    Vector bVector = Vector.fromList(b);

    double dotProduct = aVector.dot(bVector);

    double aNorm = aVector.norm();
    double bNorm = bVector.norm();

    if (aNorm == 0 || bNorm == 0) {
      return 0.0;
    } else {
      return dotProduct / (aNorm * bNorm);
    }
  }
}