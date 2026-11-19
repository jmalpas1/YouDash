# YouMod → YouDash integration (experimental)

This wrapper stages a user-supplied, decrypted and authorized **YouTube IPA 21.46.3** with the upstream **YouMod build 298 rootful** package, then runs YouDash's existing CarPlay packager. The exact supplied inputs passed metadata/decryption/package-layout preflight; the resulting app has **not yet been compiled or device-tested**. The repository's documented working input baseline is YouTube 21.42.4 + YouMod 2.0.0.

## Protect proprietary inputs

This YouDash fork is **public**. Do not commit or upload Google's YouTube IPA, YouMod-injected intermediates, resulting IPA artifacts, certificates, private keys, or provisioning profiles here. Do not publish a full IPA as an artifact or release of this public repository. Run full packaging on a Mac locally or in a **separate private repository/build environment**.

## Preflight (Windows Subsystem for Linux, macOS, or Linux)

Keep both files outside Git. Install Python 3.9+ and system `ar`, then run from the repo:

```sh
python3 scripts/build_with_youmod.py \
  --ipa /private/path/YouTube-21.46.3.ipa \
  --youmod '/private/path/YouMod build 298 rootful.zip' \
  --preflight-only
```

This checks the iOS app's metadata and Mach-O encryption information, and confirms that the .deb contains `YouMod.dylib` and `YouMod.bundle`. It does **not** establish YouTube 21.46.3 runtime compatibility.

## Build unsigned IPA on macOS

Select Xcode, then:

```sh
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-build.txt
python3 scripts/build_with_youmod.py \
  --ipa /private/path/YouTube-21.46.3.ipa \
  --youmod '/private/path/YouMod build 298 rootful.zip' \
  --bundle-id io.github.youtubecar.app \
  --reported-version native
```

The wrapper first uses pinned Cyan to inject the supplied .deb into a temporary YouTube IPA, verifies that the injection introduced `Frameworks/YouMod.dylib`, then calls `scripts/build_carplay.py --unsigned` to compile and integrate YouDash. If successful, inspect `dist/YouTubeCarPlay-21.46.3-unsigned.ipa`. This unsigned file is **not installable** until appropriately signed with an Apple provisioning profile containing the Video App entitlement.

## Known unknowns

- The upstream rootful YouMod dylib links `/Library/Frameworks/CydiaSubstrate.framework/CydiaSubstrate`; stock iOS lacks it. Cyan documents automatic ElleKit-based dependency handling, but that needs a device test.
- The second YouDash injection may disturb the first-stage YouMod dependencies. Verify the final app launches and both modules load.
- Start with the true 21.46.3 version; use the compatibility version override only after controlled testing.
- Verify the relevant CarPlay Video entitlement in the final signing profile, and test video capability on the Eonon/ZLink head unit while parked. Entitlement approval alone does not guarantee interactive website support.

This wrapper does not store or process Apple signing secrets.
