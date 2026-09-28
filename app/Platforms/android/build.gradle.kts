// Root build file for the omi-v5 Android host. The Skip skipstone output and
// the Skip runtime libraries are consumed by :app; nothing else here.
plugins {
    id("com.android.application") version "8.5.2" apply false
    id("org.jetbrains.kotlin.android") version "2.0.20" apply false
    id("org.jetbrains.kotlin.plugin.compose") version "2.0.20" apply false
}
