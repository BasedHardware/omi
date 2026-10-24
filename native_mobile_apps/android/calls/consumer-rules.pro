# Twilio Voice reaches its Java classes from native code (JNI); keep them in release builds.
-keep class com.twilio.** { *; }
-keep class tvo.webrtc.** { *; }
-dontwarn tvo.webrtc.**
-keepattributes InnerClasses
