# Stitch
Stitch is a powerful APK patching python library that allows you to inject your own java module into any APK, bundle or XAPK file.

## How it works

Will be added soon.

## Projects using Stitch:
- [WhatsAppPatcher](https://github.com/Schwartzblat/WhatsAppPatcher)- A patcher for WhatsApp Android app.
- [MoovitPatcher](https://github.com/Schwartzblat/MoovitPatcher)- A patcher for Moovit app.
- [MakoPatcher](https://github.com/Schwartzblat/MakoPatcher)- A patcher for 12+ app.

## How to use
### Installation
You can install Stitch using pip:
```bash
# For now, install the test version from TestPyPI
pip install stitch
```

### Basic Usage
Create an Android Gradle project like my smali_generator (Check it out in on of the examples) that generates the java module you want to inject.

Then, use the following code to patch an APK:
```python
from stitch import Stitch
from stitch.common import ExternalModule
from pathlib import Path

with Stitch(
        apk_path='./input.apk',
        output_apk='./output.apk',
        external_modules=[ExternalModule(Path(__file__).parent / './smali_generator',
                                         'com.smali_generator.InitProvider')]
) as stitch:
    stitch.patch()
```
And that's it! Your APK will be patched with the injected module.

The second argument to `ExternalModule` is the fully qualified name of a `ContentProvider` in your module.
Stitch registers it in the target's `AndroidManifest.xml` with a very high `initOrder`, so its `onCreate` runs
before the app's own components and your patch is loaded as early as possible.

### Registering activities and other components

Stitch merges your module's own `AndroidManifest.xml` into the target's. Declare the component in the Gradle
module the way you normally would:

```xml
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <uses-permission android:name="android.permission.INTERNET" />

    <application>
        <activity
            android:name=".SettingsActivity"
            android:exported="true"
            android:theme="@android:style/Theme.Material.Dialog" />
    </application>

</manifest>
```

and it lands in the patched APK. `activity`, `activity-alias`, `service`, `receiver` and `provider` are carried
over from `<application>`, along with root-level `uses-permission`, `uses-permission-sdk-23`, `uses-feature` and
`queries`. The target's own `<application>` and `<uses-sdk>` attributes are never touched, and a component the
target already declares is not added twice.

Two things to keep in mind:

- **Manifest attributes cannot point at your module's resources.** The target's manifest is read against the
  target's resource table, so `android:label="@string/app_name"` or `android:icon="@mipmap/ic_launcher"` would
  resolve to something unrelated. Stitch drops those attributes with a warning; framework resources
  (`@android:style/...`) are kept. Your layouts and drawables are still available at runtime -- see
  [Using your module's resources](#using-your-modules-resources).
- **A component with an `<intent-filter>` must declare `android:exported`**, otherwise Android 12+ refuses to
  install the patched APK. Stitch raises rather than guessing.

Pass `merge_module_manifests=False` to `Stitch` to turn the merge off and register only the provider.

### Adding assets

Anything under `src/main/assets/` in your module is copied into the patched APK, so you can ship data files
alongside your code and read them at runtime the usual way:

```java
InputStream stream = context.getAssets().open("my_module/config.json");
```

Each file keeps the compression AGP chose for it, which matters for assets that have to stay uncompressed to be
memory-mapped. If the app you are patching already has a file at the same path, the module's copy wins and Stitch
prints the path it replaced -- handy when you want to swap out an asset of the target app on purpose. When several
modules ship the same path, the last `ExternalModule` wins.

Assets merge cleanly because `AssetManager` reads them by path and they have no entry in `resources.arsc`.

### Using your module's resources

Your module's `res/` cannot be merged into the target's resource table: both are numbered from `0x7f`, so the same
id means different things in each. In a patched 2048, the `R.layout.activity_demo` of the example module
(`0x7f020000`) is `animator/fragment_close_enter` in the target -- `setContentView` would inflate the wrong thing.

Instead, Stitch injects your module's resource table as its own APK at `assets/stitch/<your.package>.apk`, and the
module loads it at runtime into a separate `Resources`. Because that `Resources` contains only your table, your
generated `R` constants mean exactly what they meant at compile time. `StitchResources` in the example module does
this for you:

```java
public class DemoActivity extends Activity {
    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        Context moduleContext = StitchResources.wrap(this);
        View root = LayoutInflater.from(this).cloneInContext(moduleContext).inflate(R.layout.activity_demo, null);
        setContentView(root);

        Button button = root.findViewById(R.id.demo_button);
    }
}
```

`StitchResources.wrap` returns a context whose resources are your module's; `StitchResources.get` returns the
`Resources` on its own if you want to look something up directly.

Two caveats:

- It builds the `AssetManager` by reflection, since there is no public way to construct one. `addAssetPath` is a
  non-SDK API on the *unsupported* list rather than the blocked one, and it works on Android 16 as of writing. If
  it is ever blocked, the replacement is `ResourcesLoader` (public since API 30) with the module built under a
  reserved package id.
- Theme attributes (`?attr/...`) in your layouts resolve against the theme of the activity, which belongs to the
  target app. Stick to explicit values or framework attributes.

Pass `inject_module_resources=False` to `Stitch` to skip shipping the table.

## Contributing

I will be happy if you want to contribute to this project. Feel free to open issues or submit pull requests.

## Disclaimer

For educational purpose only or something like that. I am not responsible for any misuse of this software.