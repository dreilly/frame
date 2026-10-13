#!/usr/bin/env bash
# Builds kiosk/build/homehq.apk without Gradle. Needs JDK 17 + Android build-tools 34 + platform 34:
#   brew install --cask android-commandlinetools
#   sdkmanager --sdk_root=$ANDROID_HOME "build-tools;34.0.0" "platforms;android-34"
# Install on the tablet: adb install -r kiosk/build/homehq.apk
set -euo pipefail
cd "$(dirname "$0")"

ANDROID_HOME="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
BT="$ANDROID_HOME/build-tools/34.0.0"
JAR="$ANDROID_HOME/platforms/android-34/android.jar"
# Keep using the certificate of the APK already installed on this frame. A newly
# generated key cannot update that package. The project copy is private/ignored;
# HOMEHQ_KEYSTORE can explicitly override it.
PROJECT_KS="$(cd ../.. && pwd)/backups/ms33-app-signing/homehq-debug.keystore"
KS="${HOMEHQ_KEYSTORE:-$PROJECT_KS}"
if [ ! -f "$KS" ]; then
  echo "Missing Home HQ signing key: $KS" >&2
  echo "Restore backups/ms33-app-signing/homehq-debug.keystore or set HOMEHQ_KEYSTORE." >&2
  exit 1
fi

rm -rf build && mkdir -p build/gen build/classes

"$BT/aapt2" compile --dir res -o build/res.zip
"$BT/aapt2" link -o build/base.apk -I "$JAR" --manifest AndroidManifest.xml build/res.zip \
  --java build/gen --min-sdk-version 23 --target-sdk-version 23 --version-code 3 --version-name 1.2-ms33

javac -nowarn -source 8 -target 8 -classpath "$JAR" -d build/classes \
  src/com/wesbos/homehq/*.java build/gen/com/wesbos/homehq/R.java

"$BT/d8" --min-api 23 --lib "$JAR" --output build $(find build/classes -name '*.class')
(cd build && zip -qj base.apk classes.dex)
"$BT/zipalign" -f 4 build/base.apk build/aligned.apk

"$BT/apksigner" sign --ks "$KS" --ks-pass pass:android --key-pass pass:android --out build/homehq.apk build/aligned.apk
echo "Built kiosk/build/homehq.apk"
