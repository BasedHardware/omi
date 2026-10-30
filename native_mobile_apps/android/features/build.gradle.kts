plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

android {
    namespace = "com.friend.ios.features"
    compileSdk = 36
    defaultConfig { minSdk = 29 }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures { compose = true }
}

kotlin { jvmToolchain(17) }

dependencies {
    api(project(":service"))
    api(project(":design"))
    implementation(libs.androidx.lifecycle.runtime)
    implementation(libs.androidx.browser) // sign in with Apple (web flow), and-onboarding
    // Conversations port: playback, the share FileProvider, remote images.
    implementation(libs.media3.exoplayer)
    implementation(libs.androidx.core.ktx)
    implementation(libs.coil.compose)
    testImplementation(libs.junit)
}
