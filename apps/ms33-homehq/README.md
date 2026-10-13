# Home HQ kiosk navigation

Hold two fingers still on the dashboard for 1.5 seconds to open the native controls:

- **Open launcher** opens another installed Home app, such as Rootless Launcher.
  If none is available, it opens Android Settings.
- **Android settings** opens the device's Settings app.
- **Reload dashboard** reloads the current URL.
- **Back to dashboard** dismisses the controls.

## Frames without Home or Back buttons

Some frame firmware omits Android's navigation bar. The two-finger gesture only
works inside Home HQ, so it cannot bring you back from another app's settings.

Enable **Home HQ navigation** in Android **Settings → Accessibility**. The
optional service adds floating **Back** and **Dashboard** buttons outside Home HQ:

- **Back** performs Android's normal Back action.
- **Dashboard** returns directly to Home HQ, keeping the current dashboard URL.
- Drag the dots to move the buttons. Their position is saved.

The buttons hide while Home HQ is active and return when you leave it. Android
keeps the service enabled across reboots. It requests no accessibility events or
screen-content access and does not require root. Disable **Home HQ navigation**
in Accessibility settings to remove the buttons.

Keep an ADB connection available while enabling the service on a frame with no
other way back. If needed, return to the kiosk with:

```sh
adb shell am start -n com.wesbos.homehq/.MainActivity
```

This service supplies navigation controls; it does not change the default Home
app or automatically launch the dashboard at boot.

## Build and install

Use JDK 17, Android build-tools 34.0.0, and platform 34. From the repository root:

```sh
ANDROID_HOME=/path/to/android-sdk bash apps/ms33-homehq/build.sh
adb install -r apps/ms33-homehq/build/homehq.apk
```

The build requires the ignored private key at `backups/ms33-app-signing/homehq-debug.keystore` (or `HOMEHQ_KEYSTORE` pointing to its restored copy). It deliberately refuses to generate a new key because a differently signed APK cannot update the Home HQ package already installed on the frame. The saved key and installed APK were verified to share signer certificate SHA-256 `68845378f8ac8296516e39894292405f1f0f7101bcb1c805fbeba4a089474172`.

The kiosk loads the existing hosted dashboard over the frame's Wi-Fi. A USB
connection is only needed for installation or diagnostics, not normal use.

## MS33 adaptation

This copy comes from `wesbos/photo-frame-dashboard` commit
`fbe9a30ac4f9c77d3863e19a5e98d9eadb04ab03` and adds three local changes:

- Home HQ is a HOME activity, so selecting it as the default Home launches the
  dashboard automatically after boot.
- A URL supplied with an HTTP/HTTPS VIEW intent is saved and reused on later
  HOME and boot launches.
- **Open launcher** prefers the installed KISS launcher and skips Frameo.

Set and persist the dashboard URL with:

```sh
adb shell am start -a android.intent.action.VIEW -d 'https://example.com/dashboard' \
  -n com.wesbos.homehq/.MainActivity
```

Hold two fingers for 1.5 seconds and choose **Open launcher** to reach KISS.
