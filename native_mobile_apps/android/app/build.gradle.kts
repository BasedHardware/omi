import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
}

/**
 * Build secrets, never committed: `local.properties` (git-ignored) or a Gradle property
 * (`-P`, `~/.gradle/gradle.properties`, `ORG_GRADLE_PROJECT_*`). Empty when unset.
 */
val localProperties = Properties().apply {
    rootProject.file("local.properties").takeIf { it.exists() }?.inputStream()?.use { load(it) }
}
fun secret(name: String): String = localProperties.getProperty(name) ?: providers.gradleProperty(name).orNull ?: ""

android {
    // Namespace and class names stay com.friend.ios so components
    // (MainActivity, ble services) keep the names the Flutter app registered.
    namespace = "com.friend.ios"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.friend.ios"
        minSdk = 29
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"
        // Support chat (Intercom), as iOS `OMI_INTERCOM_APP_ID` / `OMI_INTERCOM_IOS_API_KEY` and
        // Flutter's INTERCOM_APP_ID / INTERCOM_ANDROID_API_KEY. Empty: Help shows no chat row.
        buildConfigField("String", "OMI_INTERCOM_APP_ID", "\"${secret("OMI_INTERCOM_APP_ID")}\"")
        buildConfigField("String", "OMI_INTERCOM_ANDROID_API_KEY", "\"${secret("OMI_INTERCOM_ANDROID_API_KEY")}\"")
    }

    buildTypes {
        debug {
            // Separate install next to the Flutter app; talks to the local dev harness.
            applicationIdSuffix = ".native.dev"
            buildConfigField("String", "OMI_APP_PROFILE", "\"local_dev\"")
            buildConfigField("String", "OMI_API_BASE_URL", "\"http://127.0.0.1:8000/\"")
            buildConfigField("String", "OMI_AUTH_EMULATOR_HOST", "\"127.0.0.1:9099\"")
        }
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            buildConfigField("String", "OMI_APP_PROFILE", "\"production\"")
            buildConfigField("String", "OMI_API_BASE_URL", "\"https://api.omi.me/\"")
            buildConfigField("String", "OMI_AUTH_EMULATOR_HOST", "\"\"")
        }
        // Release speed (R8, not debuggable, baseline profiles) against the local dev harness: what the
        // app really feels like, installed next to the debug build's data (same id as debug).
        create("localRelease") {
            initWith(getByName("release"))
            applicationIdSuffix = ".native.dev"
            signingConfig = signingConfigs.getByName("debug")
            matchingFallbacks += listOf("release")
            buildConfigField("String", "OMI_APP_PROFILE", "\"local_dev\"")
            buildConfigField("String", "OMI_API_BASE_URL", "\"http://127.0.0.1:8000/\"")
            buildConfigField("String", "OMI_AUTH_EMULATOR_HOST", "\"127.0.0.1:9099\"")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
}

kotlin { jvmToolchain(17) }

dependencies {
    implementation(project(":features"))
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.lifecycle.runtime)
    implementation(libs.androidx.lifecycle.process)
    implementation(platform(libs.firebase.bom))
    implementation(libs.firebase.auth)
    implementation(libs.okhttp)
    implementation(libs.androidx.profileinstaller)
    implementation(libs.kotlinx.coroutines.play.services)
    // Sign in with Google (Credential Manager), and-onboarding
    implementation(libs.androidx.credentials)
    implementation(libs.androidx.credentials.play.services)
    implementation(libs.googleid)
    // System (and-onboarding): push, splash, widgets
    implementation(libs.firebase.messaging)
    implementation(libs.androidx.core.splashscreen)
    implementation(libs.androidx.glance.appwidget)
    // The Wear OS watch app (and-wear): the Wearable Data Layer.
    implementation(libs.play.services.wearable)
    // Phone calls (and-calls): Twilio Voice + Telecom
    implementation(project(":calls"))
    // Health Connect and the recording's place (and-transcribe)
    implementation(libs.health.connect)
    implementation(libs.play.services.location)
    debugImplementation(libs.compose.ui.tooling)
    testImplementation(libs.junit)
}
