<#
.SYNOPSIS
  Dry-runs the local manifest.yml through Ludusavi, without touching your real Ludusavi config.

.DESCRIPTION
  Builds a throwaway Ludusavi config in %TEMP% that:
    - disables the primary (PCGamingWiki) manifest,
    - loads this repo's manifest.yml as a local secondary manifest,
    - adds one "Home folder" root pointing at the folder that CONTAINS "Emulation".
  Then runs `ludusavi backup --preview` and prints what would be backed up.

.PARAMETER HomeRoot
  The folder that contains your Emulation folder (e.g. D:\ for D:\Emulation).

.EXAMPLE
  .\scripts\preview.ps1 -HomeRoot D:\
#>
param(
    [string]$HomeRoot = 'D:\',
    [string]$Ludusavi = 'ludusavi'
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$manifest = (Join-Path $repo 'manifest.yml') -replace '\\', '/'
$root = $HomeRoot -replace '\\', '/'
$configDir = Join-Path $env:TEMP 'ludusavi-emudeck-manifest-preview'
New-Item -ItemType Directory -Force $configDir | Out-Null

# Written without a BOM: Ludusavi rejects (and silently resets) a config.yaml that starts with one.
$config = @"
manifest:
  enable: false
  secondary:
    - path: "$manifest"
      enable: true
roots:
  - store: otherHome
    path: "$root"
"@
[IO.File]::WriteAllText((Join-Path $configDir 'config.yaml'), $config)

& $Ludusavi --config $configDir --no-manifest-update backup --preview
