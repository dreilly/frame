#!/usr/bin/env bash
# Builds apps/ms33-homehq/build/homehq.apk without Gradle. Needs JDK 17 + Android build-tools 34 + platform 34:
#   brew install --cask android-commandlinetools
#   sdkmanager --sdk_root=$ANDROID_HOME "build-tools;34.0.0" "platforms;android-34"
# Install from the repository root: adb install -r apps/ms33-homehq/build/homehq.apk
set -euo pipefail
cd "$(dirname "$0")"

ANDROID_HOME="${ANDROID_HOME:-/opt/homebrew/share/android-commandlinetools}"
BT="$ANDROID_HOME/build-tools/34.0.0"
JAR="$ANDROID_HOME/platforms/android-34/android.jar"
# Prefer an explicitly selected key, then the private key used by the original
# frame. New installations get a user-local key that must be kept for updates.
PROJECT_KS="$(cd ../.. && pwd)/backups/ms33-app-signing/homehq-debug.keystore"
USER_KS="${HOME:?}/.android/homehq-debug.keystore"
if [ -n "${HOMEHQ_KEYSTORE:-}" ]; then
  KS="$HOMEHQ_KEYSTORE"
elif [ -f "$PROJECT_KS" ]; then
  KS="$PROJECT_KS"
else
  KS="$USER_KS"
fi

if [ ! -f "$KS" ]; then
  mkdir -p "$(dirname "$KS")"
  keytool -genkeypair -keystore "$KS" -storepass android -keypass android \
    -alias homehq -keyalg RSA -keysize 2048 -validity 10000 \
    -dname "CN=Home HQ Debug,O=Home HQ,C=US"
  echo "Created Home HQ signing key: $KS"
  echo "Back up this key; future updates to this installation must use it."
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
echo "Built apps/ms33-homehq/build/homehq.apk"
