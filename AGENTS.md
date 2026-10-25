# AGENTS.md

Secondary [Ludusavi](https://github.com/mtkennerly/ludusavi) manifest that tells Ludusavi where
EmuDeck-installed emulators keep their save data, on Linux/SteamOS and Windows.

## Files

- `manifest.yml` — the manifest itself. This is the only file Ludusavi reads.
- `README.md` — user-facing setup instructions (adding the manifest URL and the "Home folder" root).
- `scripts/preview.ps1` — dry-runs the local manifest through Ludusavi with a throwaway config.
- `.agents/skills/` — task recipes for agents (e.g. adding an emulator).

## Manifest conventions

- Format follows Ludusavi's [manifest schema](https://github.com/mtkennerly/ludusavi-manifest/blob/master/data/schema.yaml).
- Top-level keys are emulator names in double quotes, sorted alphabetically (case-insensitive).
- Every path starts with `<home>/Emulation/...` (or `<home>/.var/...` etc. for Linux Flatpak data).
  Users map `<home>` to the folder that contains `Emulation` via a Ludusavi "Home folder" root.
- Each path has `tags` (`save`, `save-states`, `save-meta`) and a `when` list with `os: linux` and/or
  `os: windows`. If the same path applies to both OSes, list both under one path, not two entries.
- Use forward slashes, 2-space indentation.
- Keep the README "Supported emulators" table in sync with `manifest.yml`.

## EmuDeck layout on Windows

- Emulators install to `%APPDATA%\emudeck\Emulators\<emu>`; their save folders are junctions into
  `<drive>:\Emulation\saves\<emu>\{saves,states}`. Target the `Emulation\saves` paths, not the junctions.
- Yuzu/Citron/Eden use `Emulation\storage\<emu>\nand\user\save` (same as Linux).

## Testing

```powershell
.\scripts\preview.ps1 -HomeRoot D:\
```

Emulators with empty save folders are not listed in the preview; that's expected.
Ludusavi does not strictly filter by `when.os` for `<home>` paths, so Linux paths may also match on
Windows if the folder exists there (e.g. synced from a Steam Deck).

## itch.io manifests

`itch/scraper.py` is separate from `manifest.yml`. It reads the itch app's `butler.db`, checks the
official and the user's secondary manifests through `ludusavi manifest show --api`, scrapes
unmatched games, and writes `itch/manifests/itch-{complete,gapfill}.yml`, `itch/pcgw/*.wiki` and
`itch/report.md`. Re-runs merge into the existing manifests; `decisions.json` stores user answers.
Standard library only (no PyYAML); YAML is emitted by `to_yaml()` using `json.dumps` for scalars.
Test with `python itch/scraper.py --out <temp dir> --no-prompt`. See `itch/README.md`.
