# Ludusavi extra manifests

Additional [Ludusavi](https://github.com/mtkennerly/ludusavi) manifests for backing up save data that
Ludusavi's official manifest doesn't cover.

Forked from [hblamo/ludusavi-emudeck-manifest](https://github.com/hblamo/ludusavi-emudeck-manifest),
with Windows support added to the EmuDeck manifest and new itch.io manifests.

## Manifests

| Manifest | What it backs up | Platforms | Add this URL to Ludusavi |
|----------|------------------|-----------|--------------------------|
| [EmuDeck](#emudeck) | Emulator saves and save states for emulators installed by [EmuDeck](https://www.emudeck.com/) | Linux / SteamOS, Windows | `https://raw.githubusercontent.com/GlitchWalker/ludusavi-emudeck-manifest-mslvp/main/manifest.yml` |
| [itch.io (gap-fill)](#itchio) | Saves for itch.io games that the official manifest is missing | Windows | `https://raw.githubusercontent.com/GlitchWalker/ludusavi-emudeck-manifest-mslvp/main/itch/manifests/itch-gapfill.yml` |
| [itch.io (complete)](#itchio) | Every known itch.io game, including entries copied from the official manifest | Windows | `https://raw.githubusercontent.com/GlitchWalker/ludusavi-emudeck-manifest-mslvp/main/itch/manifests/itch-complete.yml` |

Use the itch.io **gap-fill** *or* **complete** manifest, not both. Gap-fill is the one to pick if
you keep Ludusavi's official manifest enabled, which is the default.

### Adding a manifest to Ludusavi

1. Open Ludusavi and go to the **Other** tab.
2. In the **Manifest** section, click **+** and paste the URL from the table above.
3. Add the roots listed in that manifest's section below.
4. Go to the **Backup** tab and click **Preview** to check the saves are found.

Ludusavi downloads the manifests itself and checks for updates, so there's nothing else to install.

---

## EmuDeck

Finds the save locations of emulators set up by EmuDeck, based on the
[EmuDeck wiki](https://emudeck.github.io/save-management/steamos/save-management/).

### Set up a "Home folder" root pointing at the folder that *contains* `Emulation`

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

### How saves are found on Windows

EmuDeck for Windows installs emulators to `%APPDATA%\emudeck\Emulators` and keeps the real save data
in `Emulation\saves\<emulator>\saves` and `Emulation\saves\<emulator>\states`. The emulators' own save
folders are junctions pointing there. The Windows entries in this manifest target the
`Emulation\saves` folders directly, so they don't depend on Ludusavi following junctions. The
exceptions are Yuzu, Citron and Eden, which keep saves in `Emulation\storage\<emulator>\nand\user\save`
on both platforms.

If you use the **Steam** version of RetroArch, EmuDeck makes `Emulation\saves\retroarch\saves` and
`states` symbolic links into Steam's RetroArch folder. Ludusavi's official manifest also covers Steam
RetroArch through your Steam root.

### Supported emulators

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

---

## itch.io

Ludusavi has no itch.io store type, and most itch.io games aren't on
[PCGamingWiki](https://www.pcgamingwiki.com/), the source of Ludusavi's official manifest. These
manifests fill that gap for games installed with the [itch.io desktop app](https://itch.io/app).

### Set up roots

Some games keep saves inside their own install folder. For those, add each itch.io install location
as a root of type **Other**:

| Root type | Path |
|-----------|------|
| Other | `C:\Users\<you>\AppData\Roaming\itch\apps` (the itch app's default install location) |
| Other | Any extra install location you added in itch → **Settings** → **Install locations**, e.g. `G:\ItchLibrary` |

Saves in AppData, Documents and the registry need **no** root, because Ludusavi always checks your
own profile folders.

### Generating your own: the scraper

The manifests here are built by [`itch/scraper.py`](itch/scraper.py) from real itch.io libraries, so
they only include games someone has run it on. To cover your own library, or to contribute games:

```powershell
python itch\scraper.py
```

It needs Python 3.10+ and Ludusavi, and no extra packages. For every game the itch app has installed,
it:

1. uses Ludusavi's **official manifest** if the game is there;
2. otherwise uses any **optional manifests** you've added to Ludusavi;
3. otherwise **scrapes** for saves:
   - It recognises Unity, Unreal, Godot, Ren'Py, RPG Maker, GameMaker and NW.js save locations
     automatically.
   - It asks you to confirm anything less certain, such as similarly named AppData folders and
     save-like files in the game folder.

It then writes:
- the **complete** and **gap-fill** manifests;
- **PCGamingWiki stubs**, ready to paste, for games missing from the wiki;
- a report of what was found for each game.

Re-running adds to the existing manifests instead of replacing them.

See [itch/README.md](itch/README.md) for the full details, options and limits.

### Getting games into the official manifest

The best long-term home for itch.io save locations is PCGamingWiki. Once a game's page has its save
location, it reaches everyone through Ludusavi's official manifest, and it drops out of the
gap-fill manifest the next time the scraper runs. The scraper's stubs (in `itch/pcgw/` after a run)
are a starting point for creating those pages.

---

## Development

| Path | Purpose |
|------|---------|
| `manifest.yml` | The EmuDeck manifest |
| `itch/` | itch.io scraper and generated manifests |
| `scripts/preview.ps1` | Dry-runs `manifest.yml` through Ludusavi with a throwaway config, so your real settings aren't touched |
| `AGENTS.md` | Conventions for editing the manifests (also read by AI coding agents) |

```powershell
.\scripts\preview.ps1 -HomeRoot D:\                # preview the EmuDeck manifest
python itch\scraper.py --out $env:TEMP\itch-test   # test the scraper without touching itch\
```

Manifests follow Ludusavi's
[manifest schema](https://github.com/mtkennerly/ludusavi-manifest/blob/master/data/schema.yaml).
Opening the folder in VS Code with the recommended YAML extension checks `manifest.yml` against it.

## Credits

- Original EmuDeck manifest by [hblamo](https://github.com/hblamo/ludusavi-emudeck-manifest) and contributors.
- [Ludusavi](https://github.com/mtkennerly/ludusavi) by mtkennerly.
- itch.io entries copied from the official manifest come from PCGamingWiki
  ([CC BY-NC-SA 3.0](https://creativecommons.org/licenses/by-nc-sa/3.0/)).
