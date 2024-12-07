class CreatorProfile {
  final String creatorName;
  final String creatorEmail;
  final String paypalEmail;
  final String? paypalMeLink;
  final bool? isVerified;

  CreatorProfile({
    required this.creatorName,
    required this.creatorEmail,
    required this.paypalEmail,
    this.paypalMeLink,
    this.isVerified,
  });

  factory CreatorProfile.fromJson(Map<String, dynamic> json) {
    return CreatorProfile(
      creatorName: json['creator_name'],
      creatorEmail: json['creator_email'],
      paypalEmail: json['paypal_email'],
      paypalMeLink: json['paypal_me_link'] ?? '',
      isVerified: json['is_verified'] ?? false,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'creator_name': creatorName,
      'creator_email': creatorEmail,
      'paypal_email': paypalEmail,
      'paypal_me_link': paypalMeLink ?? '',
      'is_verified': isVerified ?? false,
    };
  }

  bool isEmpty() {
    return creatorName.isEmpty && creatorEmail.isEmpty && paypalEmail.isEmpty;
  }

  static CreatorProfile empty() {
    return CreatorProfile(
      creatorName: '',
      creatorEmail: '',
      paypalEmail: '',
      paypalMeLink: '',
      isVerified: false,
    );
  }
}
