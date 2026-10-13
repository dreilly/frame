# Home HQ Android kiosk

Home HQ is a small Android HOME/WebView app that displays the hosted dashboard full-screen. It is adapted for Android 6.0/API 23 and does not require root.

You only need this app when using an Android device as the kiosk. The web dashboard can be developed and deployed without building Home HQ.

## Runtime controls

Hold two fingers still on the dashboard for 1.5 seconds to open the native controls:

- **Open launcher** opens another installed Home app, preferring KISS Launcher.
- **Android settings** opens the device Settings app.
- **Reload dashboard** reloads the current URL.
- **Back to dashboard** closes the controls.

## Configure the dashboard URL

With Android platform tools installed and USB debugging enabled, connect the device and verify it is visible:

```sh
adb devices -l
```

Set and persist the URL Home HQ should open:

```sh
adb shell am start \
  -a android.intent.action.VIEW \
  -d 'https://example.com/dashboard' \
  -n com.wesbos.homehq/.MainActivity
```

The URL can be HTTPS or a reachable LAN development URL. Do not put credentials or private feed URLs in it.

## Build requirements

- JDK 17, including `javac` and `keytool`
- Android SDK platform 34
- Android build-tools 34.0.0
- Android platform tools for `adb`

Install the required SDK packages with Android's `sdkmanager`:

```sh
sdkmanager --sdk_root="$ANDROID_HOME" "platform-tools" "build-tools;34.0.0" "platforms;android-34"
```

### macOS or Linux

From the repository root:

```sh
ANDROID_HOME=/path/to/android-sdk bash apps/ms33-homehq/build.sh
```

On Apple Silicon with Homebrew's Android command-line tools, the script's default SDK path is `/opt/homebrew/share/android-commandlinetools`, so `ANDROID_HOME` may be omitted when that path exists.

### Windows

From the repository root in PowerShell:

```powershell
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
powershell -ExecutionPolicy Bypass -File apps\ms33-homehq\build.ps1
```

Both scripts create `apps/ms33-homehq/build/homehq.apk`.

## APK signing

Android requires every APK to be signed, and future updates must use the same signing key as the installed version.

The build scripts choose a key in this order:

1. The path in `HOMEHQ_KEYSTORE`, when set.
2. The original frame's ignored private key under `backups/`, when present.
3. A user-local key at `~/.android/homehq-debug.keystore`, generated automatically when absent.

Generated keys use the development password `android`. Back up the chosen keystore somewhere private. It is not committed to the repository, and losing it means future APKs cannot update the existing installation.

To use another compatible keystore:

```sh
HOMEHQ_KEYSTORE=/private/path/homehq.keystore \
  ANDROID_HOME=/path/to/android-sdk \
  bash apps/ms33-homehq/build.sh
```

Do not share the original frame's private signing key. A friend installing Home HQ on another device should let the build create a separate key.

## Install or update

For a first installation:

```sh
adb install apps/ms33-homehq/build/homehq.apk
```

For an update signed with the same key:

```sh
adb install -r apps/ms33-homehq/build/homehq.apk
```

If Android reports an incompatible certificate, the installed app was signed with a different key. Either rebuild with its original key or uninstall it before installing the new APK:

```sh
adb uninstall com.wesbos.homehq
adb install apps/ms33-homehq/build/homehq.apk
```

Uninstalling clears Home HQ's saved URL and app settings. After installation, press Home and select Home HQ as the default HOME app, then configure the dashboard URL.

## Navigation on frames without system buttons

Some frame firmware omits Android's navigation bar. Enable **Home HQ navigation** under **Android Settings → Accessibility** to add floating **Back** and **Dashboard** buttons while outside Home HQ.

- **Back** performs Android's normal Back action.
- **Dashboard** returns to Home HQ without changing its saved URL.
- Drag the dots to reposition the controls.
- Disable **Home HQ navigation** in Accessibility to remove them.

The service requests no accessibility events or screen-content access. Keep ADB connected while enabling it on a device that has no other way to navigate back. If needed, return to Home HQ with:

```sh
adb shell am start -n com.wesbos.homehq/.MainActivity
```

## Compatibility notes

This shell is tailored to the tested Pastigio M10R5 but may work on other Android 6.0+ devices. It does not perform firmware conversion, enable USB debugging, or modify the device's default HOME selection automatically.

The adaptation adds these behaviors to the original Home HQ shell:

- It can be selected as an Android HOME activity and launch after boot.
- An HTTP or HTTPS VIEW intent saves a dashboard URL for later launches.
- **Open launcher** prefers KISS Launcher and skips Frameo.

Detailed Pastigio conversion and recovery history is in `../../docs/pastigio-m10r5.md`.
