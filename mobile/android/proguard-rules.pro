# ============================================================
# SYNAPPM - PROGUARD RULES
# Keep essential classes for Capacitor
# ============================================================

# Keep Capacitor classes
-keep class com.getcapacitor.** { *; }
-keep class com.getcapacitor.android.** { *; }
-keep class com.getcapacitor.core.** { *; }

# Keep JavaScript interfaces
-keepattributes *Annotation*
-keepattributes JavascriptInterface
-keepattributes SourceFile,LineNumberTable
-keep class android.webkit.JavascriptInterface

# Keep plugin classes
-keep class com.synapsepm.app.** { *; }

# Keep WebView classes
-keep class android.webkit.** { *; }
-keep class android.net.http.** { *; }

# Optimizations
-optimizations !code/simplification/arithmetic,!code/simplification/cast,!field/*,!class/merging/*
-optimizationpasses 5

# Don't warn about missing annotations
-dontwarn org.apache.http.**
-dontwarn android.net.http.**
-dontwarn android.webkit.**

# Keep native methods
-keepclasseswithmembernames class * {
    native <methods>;
}

# Keep serializable classes
-keepclassmembers class * implements java.io.Serializable {
    static final long serialVersionUID;
    private static final java.io.ObjectStreamField[] serialPersistentFields;
    private void writeObject(java.io.ObjectOutputStream);
    private void readObject(java.io.ObjectInputStream);
    java.lang.Object writeReplace();
    java.lang.Object readResolve();
}