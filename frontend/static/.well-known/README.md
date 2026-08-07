# Digital Asset Links (TWA verification)

Delete this file after deploying. If a real `assetlinks.json` exists alongside
this file it will be served at `/.well-known/assetlinks.json` and proves to
Android that the TWA APK owns this origin.

How to generate it (run once on a machine with JDK 17 + Android SDK):

```bash
npx @bubblewrap/cli fingerprint add <name> <sha256-fingerprint> \
    --manifest ../twa/twa-manifest.json
npx @bubblewrap/cli fingerprint generateAssetLinks \
    --output assetlinks.json
```

The `<sha256-fingerprint>` is the default SHA-256 fingerprint of the signing
keystore used to sign the APK (from `twa/android.keystore`). `bubblewrap build`
prints it, or obtain it with:

```bash
keytool -list -v -keystore ../twa/android.keystore -alias android | grep SHA256
```

The content-type must be `application/json` — it is served as-is by this
static server.