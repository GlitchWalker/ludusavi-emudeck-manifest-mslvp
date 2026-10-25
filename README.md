# ludusavi-emudeck-manifest
Additional [Ludusavi](https://github.com/mtkennerly/ludusavi) manifest for finding save location of emulators based on information on the [emudeck wiki.](https://emudeck.github.io/save-management/steamos/save-management/)

Works with EmuDeck on **Linux / SteamOS** and **Windows**.

## How To Use:

### 1. Add manifest to Ludusavi

In Ludusavi, go to the **Other** tab, find the **Manifest** section and add a new entry to the list.

Link to add: https://raw.githubusercontent.com/GlitchWalker/ludusavi-emudeck-manifest-mslvp/main/manifest.yml

### 2. Add a "Home folder" root pointing at the folder that *contains* `Emulation`

Every path in this manifest is written as `<home>/Emulation/...`. Ludusavi replaces `<home>` with your
normal home folder (`%USERPROFILE%` on Windows, `~` on Linux) **and** with every root you have added
with the type **Home folder**.

EmuDeck creates its `Emulation` folder at the root of whichever drive you picked during install, so
it is usually *not* inside your home folder. To fix that, add a root in Ludusavi:

1. Open the **Other** tab and find the **Roots** section.
2. Click **+** to add a root.
3. Set the type (store) to **Home folder**.
4. Set the path to the folder **one level above** `Emulation`, *not* the `Emulation` folder itself.

| Where EmuDeck put the Emulation folder | Root type   | Root path to enter       |
|----------------------------------------|-------------|--------------------------|
| `D:\Emulation` (Windows)               | Home folder | `D:\`                    |
| `E:\Games\Emulation` (Windows)         | Home folder | `E:\Games`               |
| `/home/deck/Emulation` (Steam Deck internal) | *(none needed, this is already `~`)* | |
| `/run/media/mmcblk0p1/Emulation` (Steam Deck SD card) | Home folder | `/run/media/mmcblk0p1` |

#### Example (Windows, Emulation folder on `D:`)

With a **Home folder** root of `D:\`, the manifest path

```
<home>/Emulation/saves/duckstation/saves
```

becomes

```
D:\Emulation\saves\duckstation\saves
```

which is exactly where EmuDeck for Windows keeps DuckStation's memory cards.

In Ludusavi's `config.yaml` (`%APPDATA%\ludusavi\config.yaml`), the root looks like this:

```yaml
roots:
  - store: otherHome
    path: "D:\\"
```

> **Common mistake:** setting the root path to `D:\Emulation`. Ludusavi would then look for
> `D:\Emulation\Emulation\saves\...`, which doesn't exist, and find nothing.

Keep any other roots you already have (Steam, GOG, etc.). The Home folder root is added *alongside* them.

### 3. Check it worked

Go to the **Backup** tab and click **Preview**. Search for an emulator name (e.g. `DuckStation`). It
should list files under your `Emulation\saves` (or `Emulation/storage`) folder. An emulator with no saves yet
won't appear in the list.

## How saves are found on Windows

EmuDeck for Windows installs emulators to `%APPDATA%\emudeck\Emulators` and keeps the real save data
in `Emulation\saves\<emulator>\saves` and `Emulation\saves\<emulator>\states`. The emulators' own save
folders are junctions pointing there. The Windows entries in this manifest target the
`Emulation\saves` folders directly, so they don't depend on Ludusavi following junctions. The
exceptions are Yuzu, Citron and Eden, which keep saves in `Emulation\storage\<emulator>\nand\user\save`
on both platforms.

If you use the **Steam** version of RetroArch, EmuDeck makes `Emulation\saves\retroarch\saves` and
`states` symbolic links into Steam's RetroArch folder. Ludusavi's main manifest also covers Steam
RetroArch through your Steam root.

## Supported emulators

| Emulator | Linux | Windows |
|----------|:-----:|:-------:|
| Azahar | ✓ | ✓ |
| BigPEmu | | ✓ |
| Cemu | ✓ | ✓ |
| Citra | ✓ | ✓ |
| Citron | ✓ | ✓ |
| Dolphin | ✓ | ✓ |
| DuckStation | ✓ | ✓ |
| Eden | ✓ | ✓ |
| Flycast | | ✓ |
| Lime3DS | | ✓ |
| MAME | ✓ | ✓ |
| melonDS | ✓ | ✓ |
| mGBA | ✓ | ✓ |
| PCSX2 | ✓ | ✓ |
| PPSSPP | ✓ | ✓ |
| PrimeHack | ✓ | ✓ |
| RetroArch | ✓ | ✓ |
| Rosalie's Mupen GUI | ✓ | ✓ |
| RPCS3 | ✓ | ✓ |
| Ryujinx | ✓ | ✓ |
| ScummVM | ✓ | ✓ |
| shadPS4 | | ✓ |
| Supermodel | | ✓ |
| Vita3K | ✓ | ✓ |
| Xemu | ✓ | ✓ |
| Xenia | ✓ | ✓ |
| Yuzu | ✓ | ✓ |

## Development

`scripts/preview.ps1` dry-runs your local `manifest.yml` through Ludusavi using a throwaway config in
`%TEMP%`, so your real Ludusavi settings aren't touched:

```powershell
.\scripts\preview.ps1 -HomeRoot D:\
```
