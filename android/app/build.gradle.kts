plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

// CI passes the build number; local builds use 1.
val buildNumber = (project.findProperty("buildNumber") as String?)?.toIntOrNull() ?: 1

android {
    namespace = "io.github.meth0gunner.healthhub"
    compileSdk = 35

    defaultConfig {
        applicationId = "io.github.meth0gunner.healthhub"
        minSdk = 29
        targetSdk = 35
        versionCode = buildNumber
        versionName = "0.1.$buildNumber"
    }

    // Every build must be signed with the same key, or Android refuses to
    // install it as an update. The key file is encrypted; its password is the
    // HH_KEYSTORE_PASSWORD secret in GitHub. Without it, builds use a debug key.
    val keystorePassword = System.getenv("HH_KEYSTORE_PASSWORD")?.takeIf { it.isNotEmpty() }
    signingConfigs {
        if (keystorePassword != null) {
            create("release") {
                storeFile = rootProject.file("signing/release.p12")
                storeType = "pkcs12"
                storePassword = keystorePassword
                keyAlias = "healthhub"
                keyPassword = keystorePassword
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            signingConfig = if (keystorePassword != null) {
                signingConfigs.getByName("release")
            } else {
                signingConfigs.getByName("debug")
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        buildConfig = true
    }
    lint {
        abortOnError = false
        checkReleaseBuilds = false
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.work:work-runtime-ktx:2.9.1")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.7")
    implementation("androidx.documentfile:documentfile:1.0.1")
}
