plugins {
    alias(libs.plugins.android.library)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.serialization)
}

// Port of omi-native `Packages/OmiDevice`: the Omi protocol (`com.friend.ios.device`) on top of
// the Flutter app's native BLE layer (`com.friend.ios.ble`, MIT), whose component names an
// in-place update over the Flutter build keeps.
android {
    namespace = "com.friend.ios.device"
    compileSdk = 36
    defaultConfig { minSdk = 29 }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

kotlin { jvmToolchain(17) }

dependencies {
    implementation(libs.kotlinx.serialization.json)
    api(libs.kotlinx.coroutines.android)
    implementation(libs.androidx.core.ktx)
    implementation(libs.mcumgr.ble)
    testImplementation(libs.junit)
}
