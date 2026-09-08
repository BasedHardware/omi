import 'package:collection/collection.dart';
import 'package:omi/backend/schema/app.dart';

/// Returns true when [updated] differs from [current] in fields shown on the app detail page.
bool hasAppDetailConfigChanged(App current, App updated) {
  if (current.name != updated.name) return true;
  if (current.description != updated.description) return true;
  return hasExternalIntegrationChanged(current.externalIntegration, updated.externalIntegration);
}

/// Returns true when external integration configuration differs between [current] and [updated].
bool hasExternalIntegrationChanged(ExternalIntegration? current, ExternalIntegration? updated) {
  const equality = DeepCollectionEquality();
  return !equality.equals(current?.toJson(), updated?.toJson());
}
