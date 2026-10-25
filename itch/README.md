# itch.io manifests for Ludusavi (Windows)

Ludusavi has no itch.io store type, and most itch games aren't on PCGamingWiki, so the official
manifest doesn't know about them. This folder has:

| File | What it is |
|------|------------|
| `manifests/itch-gapfill.yml` | **Use this one.** Only what the official manifest is missing. Add it alongside the official manifest. |
| `manifests/itch-complete.yml` | Every known itch game, including entries copied from the official manifest. Use it *instead of* the gap-fill manifest, never both. |
| `pcgw/*.wiki` | Ready-to-paste PCGamingWiki stubs for games that aren't on the wiki yet, plus "Game data" snippets for existing pages that lack Windows save locations. |
| `scraper.py` | Builds all of the above from your itch library. |
| `decisions.json` | Your answers to "back this up?" questions, so you're only asked once. |
| `report.md` | What was found for each game on the last run. |

## Using the manifest

### 1. Add the manifest

Ludusavi → **Other** → **Manifest** → **+** → URL:

```
https://raw.githubusercontent.com/GlitchWalker/ludusavi-emudeck-manifest-mslvp/main/itch/manifests/itch-gapfill.yml
```

(or choose the file option and point at your local copy of `itch-gapfill.yml`).

### 2. Add each itch install location as an "Other" root

Saves kept *inside* a game's folder are written as `<base>/...`. Ludusavi finds `<base>` by looking
for the game's itch folder name (its URL slug, e.g. `77-oleander`) **directly inside** a root of
type **Other**:

| Root type | Path |
|-----------|------|
| Other | `C:\Users\<you>\AppData\Roaming\itch\apps` (itch's default install location) |
| Other | Any extra install location you added in itch → Settings → Install locations, e.g. `G:\ItchLibrary` |

Saves in AppData, Documents and the registry need **no** root, because Ludusavi always checks your
own profile folders.

## How the scraper works

```powershell
python itch\scraper.py              # interactive: asks about uncertain paths
python itch\scraper.py --no-prompt  # just leave uncertain paths out for now
```

For every game in the itch app's database (`%APPDATA%\itch\db\butler.db`):

1. **Official manifest:** if Ludusavi's official manifest has the game (matched by title, then
   normalized title, then itch folder name), its data is used.
2. **Optional manifests:** otherwise, each secondary manifest in your Ludusavi config is checked in
   order.
3. **Scrape:** otherwise, saves are looked for:
   - **Selected automatically**, from engine conventions:
     - Unity: `LocalLow\<company>\<product>` plus the registry key
     - Unreal: `%LOCALAPPDATA%\<Project>\Saved\SaveGames`
     - Godot: `%APPDATA%\Godot\app_userdata\<name>`
     - Ren'Py: `%APPDATA%\RenPy\<save dir>` and `game\saves`
     - RPG Maker: `Save*.rvdata2` and `www\save`
     - GameMaker: `%LOCALAPPDATA%\<name>`
     - NW.js: Local Storage
   - **Selected automatically:** AppData/Documents folders whose name exactly matches the game.
   - **You're asked to confirm:** similar folder names (e.g. `SilentHill2` for *Silent Hill Remake*),
     and save-like files or folders inside the game folder (`save.txt`, `Saves\`).

   Godot/Electron cache folders (`shader_cache`, `blob_storage`, …) are left out.

If a title matches an official entry but none of that entry's save paths exist while the scraper
found saves, you're asked whether it's really the same game. Common titles like *The House* or
*Climb* often aren't.

Re-running **merges** into the existing manifests rather than replacing them, so manifests from
several people or PCs accumulate. Pass `--fresh` to rebuild from scratch.

## Contributing to PCGamingWiki

The official manifest is generated from PCGamingWiki, so getting a game onto the wiki is the best
long-term fix. Once it's there, it drops out of the gap-fill manifest on the next run.

1. Open a stub in `pcgw/`. Check the developer name and fill in anything else you know.
2. Create the page at `https://www.pcgamingwiki.com/wiki/<Game title>` and paste it in.
3. For `(game data).wiki` snippets, the page already exists. Confirm it's the same game, then
   replace its "Game data" section and add the itch.io row to its Availability table.

## Limits

- Games that have never been run, and whose engine doesn't say where they save (Godot, GameMaker,
  custom engines), are only found after they've saved once. Re-run the scraper after playing.
- Games itch only downloaded as an installer (`setup.exe`) can't be inspected; see `report.md`.
- The Unreal Engine version (4 vs 5) is guessed from the build folder layout.
- `itch-complete.yml` includes data copied from PCGamingWiki, which is licensed CC BY-NC-SA 3.0.
