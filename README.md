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
                                         'invoke-static {}, Lcom/smali_generator/TheAmazingPatch;->on_load()V')]
) as stitch:
    stitch.patch()
```
And that's it! Your APK will be patched with the injected module.

## Contributing

I will be happy if you want to contribute to this project. Feel free to open issues or submit pull requests.

## Disclaimer

For educational purpose only or something like that. I am not responsible for any misuse of this software.