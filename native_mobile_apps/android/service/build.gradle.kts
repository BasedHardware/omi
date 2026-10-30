plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.android)
    // The Omi's offline-sync queue and diagnostics are stored as JSON (and-device).
    alias(libs.plugins.kotlin.serialization)
}

android {
    namespace = "com.friend.ios.service"
    compileSdk = 36
    defaultConfig { minSdk = 29 }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

kotlin { jvmToolchain(17) }

dependencies {
    api(project(":network"))
    api(project(":persistence"))
    // The Omi wearable (and-device)
    api(project(":device"))
    api(platform(libs.compose.bom))
    api(libs.compose.runtime)
    implementation(libs.kotlinx.coroutines.android)
    // Capture (and-capture): the phone microphone (OmiAudio).
    api(project(":audio"))
    // Custom STT (and-transcribe): the provider requests are OkHttp requests.
    implementation(libs.okhttp)
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(libs.junit)
}
