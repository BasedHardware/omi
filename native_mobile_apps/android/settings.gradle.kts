pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "omi-android"

// Mirrors the SwiftPM packages of omi-native (docs/adr/0001 there):
// core <- network <- persistence <- service <- design <- features <- app
include(":core", ":network", ":persistence", ":service", ":design", ":features", ":app")
// The Omi wearable (omi-native `Packages/OmiDevice`) on the Flutter app's native BLE layer.
include(":device")
// Capture (and-capture): mirrors OmiAudio.
include(":audio")
// The Wear OS watch app (and-wear): mirrors omi-native `Watch/`; same applicationId as :app so the Data Layer pairs them.
include(":wear")
// Phone calls (and-calls): Twilio Voice + Telecom, mirrors omi-native App/PhoneCalls.
include(":calls")
