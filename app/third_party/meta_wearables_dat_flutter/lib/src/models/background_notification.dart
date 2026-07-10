/// Foreground-service notification metadata required by Android when
/// enabling background streaming.
///
/// Android prohibits silent foreground services: if your app keeps a
/// stream alive in the background, the OS requires a persistent
/// notification visible to the user. This object is forwarded to
/// `BackgroundStreamingService` and used to build the notification
/// channel + `Notification` shown while the service is running.
///
/// iOS has no equivalent requirement; pass `null` to
/// [MetaWearablesDat.enableBackgroundStreaming] on iOS.
class BackgroundNotification {
  /// Creates a [BackgroundNotification].
  const BackgroundNotification({
    required this.title,
    required this.text,
    required this.channelId,
    required this.channelName,
    this.iconResourceName,
  });

  /// Title text on the notification.
  final String title;

  /// Body text on the notification.
  final String text;

  /// Notification channel id. Apps may reuse an existing channel id;
  /// the plugin only creates a channel when one with this id does not
  /// already exist.
  final String channelId;

  /// Notification channel display name (shown in Android Settings >
  /// Apps > Notifications).
  final String channelName;

  /// Optional Android drawable resource name (no extension) used as
  /// the notification's small icon. When `null`, the plugin falls back
  /// to the app's launcher icon.
  final String? iconResourceName;

  /// Serialises to the platform-channel argument map consumed by the
  /// Android side.
  Map<String, Object?> toMap() => <String, Object?>{
        'title': title,
        'text': text,
        'channelId': channelId,
        'channelName': channelName,
        if (iconResourceName != null) 'iconResourceName': iconResourceName,
      };
}
