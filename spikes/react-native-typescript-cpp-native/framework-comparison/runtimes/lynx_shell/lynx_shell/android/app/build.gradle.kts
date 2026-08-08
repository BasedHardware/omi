plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.jetbrains.kotlin.android)
}

android {
    namespace = "com.lynxshell"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.lynxshell"
        minSdk = 24
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables {
            useSupportLibrary = true
        }
    }

    signingConfigs {
        create("release") {
            storeFile = file("release-key.keystore")
            storePassword = "release"
            keyAlias = "release-key-alias"
            keyPassword = "release-key-password"
        }
    }

    buildTypes {
        debug {
            isDebuggable = true
            applicationIdSuffix = ".debug"
        }
        release {
            isMinifyEnabled = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
            signingConfig = signingConfigs.getByName("release")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_1_8
        targetCompatibility = JavaVersion.VERSION_1_8
    }
    kotlinOptions {
        jvmTarget = "1.8"
    }
    buildFeatures {
        buildConfig = true
        compose = true
    }
    composeOptions {
        kotlinCompilerExtensionVersion = "1.5.1"
    }
    packaging {
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

dependencies {

    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.ui)
    implementation(libs.androidx.ui.graphics)
    implementation(libs.androidx.ui.tooling.preview)
    implementation(libs.androidx.material3)
    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.ui.test.junit4)
    debugImplementation(libs.androidx.ui.tooling)
    debugImplementation(libs.androidx.ui.test.manifest)

    implementation("com.squareup.retrofit2:retrofit:2.7.0")

    // lynx dependencies
    implementation("org.lynxsdk.lynx:lynx:3.4.1")
    implementation("org.lynxsdk.lynx:lynx-jssdk:3.4.1")
    implementation("org.lynxsdk.lynx:lynx-trace:3.4.1")
    implementation("org.lynxsdk.lynx:primjs:2.14.1")

    // integrating image-service
    implementation("org.lynxsdk.lynx:lynx-service-image:3.4.1")

    // image-service dependencies, if not added, images cannot be loaded; if the host APP needs to use other image libraries, you can customize the image-service and remove this dependency
    implementation("com.facebook.fresco:fresco:2.3.0")
    implementation("com.facebook.fresco:animated-gif:2.3.0")
    implementation("com.facebook.fresco:animated-webp:2.3.0")
    implementation("com.facebook.fresco:webpsupport:2.3.0")
    implementation("com.facebook.fresco:animated-base:2.3.0")

    // integrating log-service
    implementation("org.lynxsdk.lynx:lynx-service-log:3.4.1")

    // integrating http-service
    implementation("org.lynxsdk.lynx:lynx-service-http:3.4.1")

    implementation("com.squareup.okhttp3:okhttp:4.9.0")

    // add devtool's dependencies
    implementation ("org.lynxsdk.lynx:lynx-devtool:3.4.1")
    implementation ("org.lynxsdk.lynx:lynx-service-devtool:3.4.1")

    // add xelement's dependencies
    implementation ("org.lynxsdk.lynx:xelement:3.4.1")
    implementation ("org.lynxsdk.lynx:xelement-input:3.4.1")
}