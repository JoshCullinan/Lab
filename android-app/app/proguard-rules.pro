# LabTrack Viewer ProGuard Rules

# Keep Hilt generated classes
-keep class dagger.hilt.** { *; }
-keep class javax.inject.** { *; }
-keep class * extends dagger.hilt.android.internal.managers.ViewComponentManager$FragmentContextWrapper { *; }

# Keep WebView JavaScript interface
-keepclassmembers class com.labtrack.viewer.domain.webview.WebViewJsInterface {
    @android.webkit.JavascriptInterface <methods>;
}

# PDFBox Android
-keep class com.tom_roush.pdfbox.** { *; }
-dontwarn com.tom_roush.pdfbox.**

# ML Kit
-keep class com.google.mlkit.** { *; }

# ViewModel — keep constructors for Hilt injection
-keepclassmembers class * extends androidx.lifecycle.ViewModel {
    <init>(...);
}

# Navigation — keep argument classes
-keepnames class androidx.navigation.** { *; }

# Data models — keep names for JSON parsing via org.json
-keepnames class com.labtrack.viewer.data.models.** { *; }

# EncryptedSharedPreferences
-keep class androidx.security.crypto.** { *; }
