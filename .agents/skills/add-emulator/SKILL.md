---
name: add-emulator
description: Add or update an emulator's save paths in manifest.yml for Linux and/or Windows EmuDeck installs.
---

# Add or update an emulator

1. Find the save locations:
   - Linux: the [EmuDeck save management wiki](https://emudeck.github.io/save-management/steamos/save-management/).
   - Windows: look in `<drive>:\Emulation\saves\<emu>\` and check which folders under
     `%APPDATA%\emudeck\Emulators\<emu>\` are junctions into it:
     ```powershell
     Get-ChildItem "$env:APPDATA\emudeck\Emulators\<emu>" -Recurse -Depth 4 -Force -Attributes ReparsePoint |
       % { "$($_.FullName) -> $($_.Target)" }
     ```
2. Add the entry to `manifest.yml` in alphabetical position, following the conventions in `AGENTS.md`
   (`<home>/Emulation/...` paths, `tags`, `when: - os: ...`).
3. Add or update the row in the README "Supported emulators" table.
4. Run `.\scripts\preview.ps1 -HomeRoot D:\` and confirm the emulator appears (it only appears if
   its save folder contains files).
