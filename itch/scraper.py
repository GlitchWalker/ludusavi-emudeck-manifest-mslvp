"""Build Ludusavi manifests and PCGamingWiki stubs for games installed by the itch.io desktop app.

For every game the itch app has installed (read from %APPDATA%\\itch\\db\\butler.db):
  1. If Ludusavi's official manifest knows the game, use that data.
  2. Otherwise, if one of your optional (secondary) manifests knows it, use that data.
  3. Otherwise scrape for save data:
       - engine conventions (Unity, Unreal, Godot, Ren'Py, RPG Maker, GameMaker, NW.js) are selected
         automatically;
       - folders in AppData/Documents/Saved Games whose name matches the game are selected
         automatically when the match is exact, and offered for confirmation when it is fuzzy;
       - save-like files/folders inside the install folder are offered for confirmation.
     Answers are remembered in decisions.json, so you are only asked once.

Outputs (in --out, default: next to this script):
  manifests/itch-complete.yml  every installed itch game, from whichever source knew it
  manifests/itch-gapfill.yml   only what the official manifest is missing (use alongside it)
  pcgw/*.wiki                  PCGamingWiki stubs for games not in the official manifest, and
                               "Game data" snippets for official games that lack Windows save paths
  report.md                    what was found for each game

Existing manifests in --out are merged with, not replaced, so results from several PCs accumulate.

Standard library only. Requires Ludusavi (used to read the manifests).
"""

import argparse
import difflib
import glob
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
APPDATA = Path(os.environ.get("APPDATA", ""))
LOCALAPPDATA = Path(os.environ.get("LOCALAPPDATA", ""))
HOME = Path.home()
LOCALLOW = HOME / "AppData" / "LocalLow"
DOCUMENTS = HOME / "Documents"
LUDUSAVI_DIR = APPDATA / "ludusavi"
OUTPUT_MANIFESTS = ("itch-complete.yml", "itch-gapfill.yml")

# (folder on this machine, manifest placeholder, depth of game folders, engine-specific?)
# Placeholders follow the official manifest's conventions (e.g. <home>/AppData/LocalLow).
SAVE_ROOTS = [
    (APPDATA / "Godot" / "app_userdata", "<winAppData>/Godot/app_userdata", 1, True),
    (APPDATA / "RenPy", "<winAppData>/RenPy", 1, True),
    (APPDATA / "LOVE", "<winAppData>/LOVE", 1, True),
    (LOCALLOW, "<home>/AppData/LocalLow", 2, True),
    (APPDATA, "<winAppData>", 1, False),
    (LOCALAPPDATA, "<winLocalAppData>", 1, False),
    (DOCUMENTS / "My Games", "<winDocuments>/My Games", 1, False),
    (DOCUMENTS, "<winDocuments>", 1, False),
    (HOME / "Saved Games", "<home>/Saved Games", 1, False),
]

# Folder names under the save roots that are never one game's save folder.
IGNORED_DIRS = {
    "microsoft", "google", "mozilla", "packages", "programs", "temp", "itch", "ludusavi", "emudeck",
    "steam", "discord", "nvidia", "nvidiacorporation", "amd", "intel", "unity", "unitycrashhandler",
    "crashdumps", "godot", "renpy", "love", "mygames", "github", "code", "npm", "pip", "python",
    "adobe", "apple", "docker", "jetbrains", "savedgames", "videos", "pictures", "music", "downloads",
}

# Godot/NW.js/Electron regenerate these on every run; they can be tens of MB and aren't save data.
CACHE_DIRS = {
    "shader_cache", "vulkan", "logs", "cache", "code cache", "gpucache", "crashpad", "blob_storage",
    "dawncache", "dawngraphitecache", "dawnwebgpucache", "grshadercache", "shadercache",
    "gpupersistentcache", "network", "session storage", "shared dictionary", "service worker",
    # Browser login/network state, not saves (and private).
    "cookies", "cookies-journal", "network persistent state", "transportsecurity", "trust tokens",
    "trust tokens-journal", "reporting and nel", "reporting and nel-journal",
}

SAVE_NAME = re.compile(
    r"^(saves?|savegames?|saved ?games?|savedata|savefiles?|profiles?)$"
    r"|^save.*\.(dat|json|sav|txt|ini|bin)$|\.(sav|save|es3)$|^save\d*\.r[xv]data2?$",
    re.I,
)
HELPER_EXE = re.compile(r"unitycrashhandler|crashreport|unins|setup|vc_?redist|dxsetup|ue4prereq|dotnet|oalinst|notification_helper", re.I)
VERSION_NOISE = re.compile(
    r"(?:[ _\-.]*(?:v?\d+(?:[._]\d+)+[a-z]?|v\d+|win(?:dows)?(?:64|32)?|x64|x86|64bit|32bit|pc|build|release|final|jam(?:edition)?|setup))+$",
    re.I,
)
MAX_DEPTH = 5


def norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.lower())


def norm_loose(name: str) -> str:
    """norm() without bracketed suffixes like "(free)" or "[Full Game]"."""
    return norm(re.sub(r"[\(\[][^\)\]]*[\)\]]", "", name))


def windows_safe(s: str) -> str:
    # Unity and others replace characters that are invalid in Windows file names with "_".
    return re.sub(r'[<>:"/\\|?*]', "_", s.strip())


# ---------------------------------------------------------------------------------------------
# itch.io database
# ---------------------------------------------------------------------------------------------

@dataclass
class Game:
    title: str
    slug: str
    url: str
    creator: str
    published: str
    free: bool
    install: Path
    install_dir: str | None          # folder name under an install location (None = custom folder)
    base: str                        # "<base>" or the custom folder's absolute path
    exe_dir: Path                    # folder containing the main executable
    engines: dict = field(default_factory=dict)   # PCGW engine name -> build/version ("" if unknown)
    auto: dict = field(default_factory=dict)      # manifest path -> reason
    ask: dict = field(default_factory=dict)       # manifest path -> reason
    registry: dict = field(default_factory=dict)  # registry path -> reason

    def manifest_path(self, p: Path) -> str:
        """Path inside the install folder -> <base>/..., with version-named wrapper folders as '*'."""
        try:
            rest = p.relative_to(self.exe_dir)
            wrapper = ["*"] * len(self.exe_dir.relative_to(self.install).parts)
        except ValueError:
            rest, wrapper = p.relative_to(self.install), []
        return "/".join([self.base, *wrapper, *rest.parts]) if (wrapper or rest.parts) else self.base


def read_itch(db_path: Path):
    """Return (games, skipped, install locations)."""
    # Read a copy so we never lock the database while the itch app is running.
    with tempfile.TemporaryDirectory() as tmp:
        copy = Path(tmp) / "butler.db"
        shutil.copyfile(db_path, copy)
        db = sqlite3.connect(copy)
        try:
            locations = dict(db.execute("select id, path from install_locations"))
            rows = db.execute(
                "select c.install_location_id, c.install_folder_name, c.custom_install_folder, c.verdict, "
                "g.title, g.url, g.published_at, g.min_price, g.classification, u.display_name, u.username "
                "from caves c join games g on g.id = c.game_id left join users u on u.id = g.user_id "
                "order by g.title collate nocase"
            ).fetchall()
        finally:
            db.close()

    games, skipped = [], []
    for loc, folder, custom, verdict, title, url, published, min_price, cls, display, username in rows:
        if cls != "game":
            skipped.append((title, f"itch classification '{cls}'"))
            continue
        if custom:
            install, base, install_dir = Path(custom), Path(custom).as_posix(), None
        else:
            install, base, install_dir = Path(locations.get(loc, "")) / folder, "<base>", folder
        if not install.is_dir():
            skipped.append((title, "install folder missing (stale itch entry)"))
            continue

        candidates = (json.loads(verdict or "{}").get("candidates")) or []
        exes = [c for c in candidates if c.get("flavor") == "windows" and not HELPER_EXE.search(c.get("path", ""))]
        if exes:
            exe = install / min(exes, key=lambda c: c.get("depth", 99))["path"]
        else:
            found = sorted(
                (p for p in install.rglob("*.exe") if ".itch" not in p.parts and not HELPER_EXE.search(p.name)),
                key=lambda p: len(p.parts),
            )
            if not found:
                flavors = sorted({c.get("flavor", "?") for c in candidates})
                why = ("only an installer/helper .exe (run the installer, then add the game manually)" if "windows" in flavors
                       else f"not a Windows game ({', '.join(flavors)})" if flavors else "no executable found")
                skipped.append((title, why))
                continue
            exe = found[0]

        host = re.match(r"https?://([^.]+)\.itch\.io", url or "")
        games.append(Game(
            title=title,
            slug=(url or "").rstrip("/").rsplit("/", 1)[-1],
            url=url or "",
            creator=display or username or (host.group(1) if host else ""),
            published=published or "",
            free=not min_price,
            install=install,
            install_dir=install_dir,
            base=base,
            exe_dir=exe.parent,
        ))
    return games, skipped, list(locations.values())


# ---------------------------------------------------------------------------------------------
# Manifests (read through Ludusavi itself, so parsing always matches what Ludusavi does)
# ---------------------------------------------------------------------------------------------

def find_ludusavi(explicit: str | None) -> str:
    exe = explicit or shutil.which("ludusavi")
    if not exe:
        winget = LOCALAPPDATA / "Microsoft" / "WinGet" / "Packages"
        found = sorted(winget.glob("mtkennerly.ludusavi_*/ludusavi.exe"))
        exe = str(found[0]) if found else None
    if not exe:
        sys.exit("Ludusavi not found. Install it, put it on PATH, or pass --ludusavi <path to ludusavi.exe>.")
    return exe


def dump_manifest(ludusavi: str, primary: bool, secondary: list) -> dict:
    """Run `ludusavi manifest show --api` against a throwaway config and return the JSON."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        for cached in LUDUSAVI_DIR.glob("manifest*.yaml"):
            shutil.copyfile(cached, tmp / cached.name)
        lines = ["manifest:", f"  enable: {'true' if primary else 'false'}", "  secondary:"]
        for s in secondary:
            key = "url" if "url" in s else "path"
            lines += [f"    - {key}: {json.dumps(s[key])}", "      enable: true"]
        if not secondary:
            lines[-1] = "  secondary: []"
        (tmp / "config.yaml").write_text("\n".join(lines) + "\n", encoding="utf-8")
        missing = (primary and not (tmp / "manifest.yaml").exists()) or any("url" in s for s in secondary)
        update = ["--try-manifest-update"] if missing else ["--no-manifest-update"]
        out = subprocess.run(
            [ludusavi, "--config", str(tmp), *update, "manifest", "show", "--api"],
            capture_output=True, check=True,
        ).stdout
    return json.loads(out.decode("utf-8")) if out.strip() else {}


def user_secondaries(exclude_dir: Path) -> list:
    """Secondary manifests from the user's Ludusavi config, minus this script's own outputs."""
    config = LUDUSAVI_DIR / "config.yaml"
    if not config.is_file():
        return []
    result, in_secondary, current = [], False, None
    for line in config.read_text(encoding="utf-8", errors="replace").splitlines():
        if re.match(r"^\S", line):
            in_secondary = False
        if re.match(r"^\s+secondary:", line):
            in_secondary = True
            continue
        if not in_secondary:
            continue
        m = re.match(r"^\s*-?\s*(url|path):\s*\"?(.*?)\"?\s*$", line)
        if m:
            current = {m.group(1): m.group(2).replace("\\\\", "\\")}
            result.append(current)
        m = re.match(r"^\s+enable:\s*(\w+)", line)
        if m and current is not None:
            current["enable"] = m.group(1) == "true"
    own = {str((exclude_dir / "manifests" / n).resolve()).lower() for n in OUTPUT_MANIFESTS}
    return [
        s for s in result
        if s.get("enable", True)
        and not any(n in (s.get("url") or s.get("path") or "") for n in OUTPUT_MANIFESTS)
        and str(Path(s.get("path", "~nonexistent~")).resolve()).lower() not in own
    ]


class ManifestIndex:
    def __init__(self, name: str, data: dict):
        self.name, self.data = name, data
        self.exact, self.normal, self.loose, self.install = {}, {}, {}, {}
        for title, entry in data.items():
            target = entry.get("alias") or title
            self.exact.setdefault(title.lower(), target)
            self.normal.setdefault(norm(title), target)
            self.loose.setdefault(norm_loose(title), target)
            for d in entry.get("installDir") or {}:
                if len(norm(d)) >= 5:
                    self.install.setdefault(norm(d), target)

    def match(self, game: Game):
        """Return (title, how) or (None, None)."""
        for key, table, how in (
            (game.title.lower(), self.exact, "title"),
            (norm(game.title), self.normal, "normalized title"),
            (norm_loose(game.title), self.loose, "title without bracketed suffix"),
        ):
            if key and key in table and table[key] in self.data:
                return table[key], how
        # Only the itch slug: folder names inside the download (e.g. "Liminal", "WindowsNoEditor") are
        # too generic and matched unrelated Steam games.
        d = game.install_dir or ""
        if norm(d) in self.install and norm(d) not in GENERIC_FOLDERS:
            return self.install[norm(d)], f"installDir '{d}'"
        return None, None


# Build-output folder names that say nothing about which game they belong to.
GENERIC_FOLDERS = {
    "windowsnoeditor", "windows", "win", "win64", "win32", "x64", "x86", "bin", "binaries", "game", "pc",
    "build", "builds", "release", "data", "content", "export", "exports", "standalone",
}


def has_windows_saves(entry: dict) -> bool:
    for path, info in (entry.get("files") or {}).items():
        when = (info or {}).get("when") or []
        oses = {w.get("os") for w in when if w.get("os")}
        if not oses or "windows" in oses:
            if not path.startswith(("<xdg", "<home>/Library", "<home>/.")):
                return True
    return bool(entry.get("registry"))


# ---------------------------------------------------------------------------------------------
# Scraping
# ---------------------------------------------------------------------------------------------

def walk(root: Path):
    root_depth = len(root.parts)
    for dp, dns, fns in os.walk(root):
        d = Path(dp)
        dns[:] = [n for n in dns if n != ".itch"]
        if len(d.parts) - root_depth >= MAX_DEPTH:
            dns[:] = []
        yield d, dns, fns


def read_head(path: Path, size: int = 4096) -> bytes:
    try:
        with path.open("rb") as fh:
            return fh.read(size)
    except OSError:
        return b""


def detect(game: Game) -> set:
    """Fill in engines, auto paths and registry from engine conventions. Returns candidate names."""
    names = {game.title, game.slug, game.exe_dir.name}
    names.update(n for n in os.listdir(game.install) if n != ".itch")

    for d, dns, fns in walk(game.install):
        lower = {f.lower() for f in fns}

        if d.name.endswith("_Data") and lower & {"globalgamemanagers", "maindata", "app.info", "data.unity3d"}:
            build = ""
            for f in ("globalgamemanagers", "data.unity3d", "mainData"):
                m = re.search(rb"(20\d\d\.\d+\.\d+[abfp]\d+|[345]\.\d+\.\d+[abfp]\d+)", read_head(d / f))
                if m:
                    build = m.group(1).decode()
                    break
            game.engines["Unity"] = build
            product = d.name[: -len("_Data")]
            names.add(product)
            info = d / "app.info"
            lines = info.read_text(encoding="utf-8", errors="replace").splitlines() if info.is_file() else []
            if len(lines) >= 2 and lines[0].strip() and lines[1].strip():
                company, product = windows_safe(lines[0]), windows_safe(lines[1])
                names.add(product)
                game.auto[f"<home>/AppData/LocalLow/{company}/{product}"] = "Unity (app.info)"
                game.registry[f"HKEY_CURRENT_USER/Software/{company}/{product}"] = "Unity PlayerPrefs"
            else:
                game.auto[f"<home>/AppData/LocalLow/*/{product}"] = "Unity (no app.info, company unknown)"

        if "Binaries" in dns and "Content" in dns and d.name != "Engine":
            parts = {p.lower() for p in d.parts}
            version = "Unreal Engine 4" if "windowsnoeditor" in parts else "Unreal Engine 5" if "windows" in parts else "Unreal Engine 4"
            game.engines.setdefault(version, "")
            names.add(d.name)
            game.auto[f"<winLocalAppData>/{d.name}/Saved/SaveGames"] = "Unreal"
            game.auto[game.manifest_path(d / "Saved" / "SaveGames")] = "Unreal (portable)"

        for f in fns:
            if f.lower().endswith(".pck"):
                head = read_head(d / f, 20)
                ver = ""
                if head[:4] == b"GDPC":
                    major, minor, patch = (int.from_bytes(head[i:i + 4], "little") for i in (8, 12, 16))
                    ver = f"{major}.{minor}.{patch}"
                game.engines.setdefault("Godot", ver)

        if "renpy" in dns and "game" in dns:
            vc = (d / "renpy" / "vc_version.py")
            m = re.search(r"version\s*=\s*['\"]([\d.]+)", vc.read_text(errors="replace")) if vc.is_file() else None
            game.engines["Ren'Py"] = ".".join(m.group(1).split(".")[:3]) if m else ""
            game.auto[game.manifest_path(d / "game" / "saves")] = "Ren'Py (game folder)"
            opt = d / "game" / "options.rpy"
            if opt.is_file():
                m = re.search(r"config\.save_directory\s*=\s*['\"]([^'\"]+)['\"]", opt.read_text(encoding="utf-8", errors="replace"))
                if m:
                    game.auto[f"<winAppData>/RenPy/{m.group(1)}"] = "Ren'Py (options.rpy)"

        for ext, name in ((".rgssad", "RPG Maker XP"), (".rgss2a", "RPG Maker"), (".rgss3a", "RPG Maker VX Ace")):
            if any(f.endswith(ext) for f in lower):
                game.engines.setdefault(name, "")
                game.auto[game.manifest_path(d) + "/Save*.r*data*"] = name
        if "rpg_core.js" in lower or "rmmz_core.js" in lower:
            game.engines.setdefault("RPG Maker", "MZ" if "rmmz_core.js" in lower else "MV")
            root = d.parent.parent if d.name == "js" else d
            game.auto[game.manifest_path(root / "save")] = "RPG Maker MV/MZ"

        if "data.win" in lower:
            game.engines.setdefault("GameMaker", "")
            for f in fns:
                if f.lower().endswith(".exe") and not HELPER_EXE.search(f):
                    game.auto[f"<winLocalAppData>/{f[:-4]}"] = "GameMaker (game name = exe name)"

        if "nw.dll" in lower:
            game.engines.setdefault("NW.js", "")
            pkg = d / "package.json"
            if pkg.is_file():
                try:
                    app = json.loads(pkg.read_text(encoding="utf-8")).get("name")
                except (ValueError, OSError):
                    app = None
                if app:
                    game.auto[f"<winLocalAppData>/{app}/User Data/Default/Local Storage"] = "NW.js (package.json)"
                    game.auto[f"<winLocalAppData>/{app}/User Data/Default/IndexedDB"] = "NW.js (package.json)"
        if (d / "resources" / "app.asar").is_file():
            game.engines.setdefault("Electron", "")
        if "love.dll" in lower:
            game.engines.setdefault("LÖVE", "")

        for n in dns + fns:
            if SAVE_NAME.search(n):
                p = game.manifest_path(d / n)
                if p not in game.auto and not any(p.startswith(a.rstrip("*")) for a in game.auto):
                    game.ask[p] = "save-like name in the game folder"

        for f in fns:
            if f.lower().endswith(".exe") and not HELPER_EXE.search(f):
                names.add(f[:-4])
    return names


def candidate_keys(names) -> set:
    out = set()
    for n in names:
        if not n:
            continue
        n = re.sub(r"\.exe$", "", n, flags=re.I)
        for v in (n, VERSION_NOISE.sub("", n), re.sub(r"[\(\[][^\)\]]*[\)\]]", "", n)):
            k = norm(v)
            if len(k) >= 5:
                out.add(k)
    return out


def index_save_roots() -> dict:
    """normalized folder name -> [(placeholder path, engine-specific root?)] for folders that exist."""
    index = {}
    for folder, placeholder, depth, specific in SAVE_ROOTS:
        if not folder.is_dir():
            continue
        level = [(folder, placeholder)]
        for _ in range(depth):
            nxt = []
            for f, p in level:
                try:
                    children = [c for c in f.iterdir() if c.is_dir()]
                except OSError:
                    continue
                nxt += [(c, f"{p}/{c.name}") for c in children if norm(c.name) not in IGNORED_DIRS]
            level = nxt
        for f, p in level:
            for q in without_caches(f, p):
                index.setdefault(norm(f.name), []).append((q, specific))
    return index


def without_caches(folder: Path, placeholder: str) -> list:
    try:
        children = list(folder.iterdir())
    except OSError:
        return [placeholder]
    if not any(c.name.lower() in CACHE_DIRS for c in children):
        return [placeholder]
    return [f"{placeholder}/{c.name}" for c in children if c.name.lower() not in CACHE_DIRS]


def match_save_folders(game: Game, names: set, index: dict):
    keys = candidate_keys(names)
    for key in keys:
        for path, specific in index.get(key, []):
            if specific or len(key) >= 8:
                game.auto.setdefault(path, "folder name matches the game")
            else:
                game.ask.setdefault(path, "short folder name matches the game")
    for folder_key, entries in index.items():
        if folder_key in keys or len(folder_key) < 5:
            continue
        for key in keys:
            shorter, longer = sorted((key, folder_key), key=len)
            contained = shorter in longer and len(shorter) / len(longer) >= 0.6
            if contained or difflib.SequenceMatcher(None, key, folder_key).ratio() >= 0.85:
                for path, _ in entries:
                    if path not in game.auto:
                        game.ask.setdefault(path, f"folder name is similar to '{key}'")
                break


# ---------------------------------------------------------------------------------------------
# Confirmation
# ---------------------------------------------------------------------------------------------

def resolve(path: str, game: Game) -> str:
    """Placeholder path -> a real path on this PC, for showing to the user."""
    for placeholder, real in (
        ("<home>/AppData/LocalLow", LOCALLOW), ("<winAppData>", APPDATA), ("<winLocalAppData>", LOCALAPPDATA),
        ("<winDocuments>", DOCUMENTS), ("<home>", HOME), ("<base>", game.install),
    ):
        if path.startswith(placeholder):
            return str(real) + path[len(placeholder):].replace("/", "\\")
    return path


def exists_on_disk(path: str, game: Game) -> bool:
    pattern = re.sub(r"<[^>]+>", "*", resolve(path, game))
    try:
        return any(True for _ in glob.iglob(pattern))
    except (OSError, ValueError):
        return False


def same_game(game: Game, title: str, how: str, entry: dict, decisions: dict, prompt: bool) -> bool:
    """A title match is trusted unless the entry's saves are absent while scraped saves are present."""
    if not how.endswith("title"):
        return True
    known = decisions.setdefault(game.slug, {"accept": [], "reject": []})
    if "same_as" in known and known["same_as"].get("title") == title:
        return known["same_as"]["same"]
    files, registry = windows_paths(entry)
    if not files or any(exists_on_disk(p, game) for p in files):
        return True
    if not any(exists_on_disk(p, game) for p in game.auto):
        return True
    if not prompt:
        return True
    print(f"\n== {game.title} ({game.url})")
    print(f"  The manifest has an entry called '{title}', but none of its save paths exist here:")
    for p in files[:3]:
        print(f"    {p}")
    print("  while these were found for the itch game:")
    for p in [p for p in game.auto if exists_on_disk(p, game)][:3]:
        print(f"    {resolve(p, game)}")
    answer = ""
    while answer not in {"y", "n"}:
        answer = input("  Is it the same game? [y]es / [n]o: ").strip().lower()
    known["same_as"] = {"title": title, "same": answer == "y"}
    return answer == "y"


def confirm(games: list, decisions: dict, prompt: bool) -> int:
    """Move accepted 'ask' paths into 'auto'. Returns how many are still undecided."""
    pending = 0
    stop = not prompt
    for game in games:
        known = decisions.setdefault(game.slug, {"accept": [], "reject": []})
        undecided = [p for p in sorted(game.ask) if p not in known["accept"] and p not in known["reject"]]
        if undecided and not stop:
            print(f"\n== {game.title}  ({', '.join(game.engines) or 'engine unknown'}) — {game.url}")
        accept_rest = False
        for p in undecided:
            if stop:
                pending += 1
                continue
            if accept_rest:
                known["accept"].append(p)
                continue
            shown = next(glob.iglob(re.sub(r"<[^>]+>", "*", resolve(p, game))), resolve(p, game))
            print(f"  {game.ask[p]}:\n    {shown}")
            while True:
                answer = input("  Back this up? [y]es / [n]o / [a]ll for this game / [s]kip game / [q]uit asking: ").strip().lower()
                if answer in {"y", "n", "a", "s", "q"}:
                    break
            if answer == "y":
                known["accept"].append(p)
            elif answer == "n":
                known["reject"].append(p)
            elif answer == "a":
                known["accept"].append(p)
                accept_rest = True
            elif answer == "s":
                pending += len(undecided) - undecided.index(p)
                break
            else:
                stop = True
                pending += len(undecided) - undecided.index(p)
        for p in known["accept"]:
            if p in game.ask:
                game.auto[p] = game.ask.pop(p) + " (confirmed)"
    return pending


# ---------------------------------------------------------------------------------------------
# Output: manifests
# ---------------------------------------------------------------------------------------------

def to_yaml(value, indent: int = 0) -> list:
    pad = "  " * indent
    lines = []
    if isinstance(value, dict):
        for k, v in value.items():
            key = json.dumps(str(k), ensure_ascii=False)
            if isinstance(v, (dict, list)) and v:
                lines.append(f"{pad}{key}:")
                lines += to_yaml(v, indent + 1)
            else:
                lines.append(f"{pad}{key}: {scalar(v)}")
    else:
        for v in value:
            if isinstance(v, dict) and v:
                sub = to_yaml(v, indent + 1)
                lines.append(f"{pad}- {sub[0].lstrip()}")
                lines += sub[1:]
            else:
                lines.append(f"{pad}- {scalar(v)}")
    return lines


def scalar(v) -> str:
    if v == {}:
        return "{}"
    if v == []:
        return "[]"
    if v is None:
        return "~"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    return json.dumps(str(v), ensure_ascii=False)


def scraped_entry(game: Game) -> dict:
    entry = {}
    if game.install_dir:
        entry["installDir"] = {game.install_dir: {}}
    if game.auto:
        entry["files"] = {p: {"tags": ["save"], "when": [{"os": "windows"}]} for p in sorted(game.auto, key=str.lower)}
    if game.registry:
        entry["registry"] = {r: {"tags": ["save", "config"]} for r in sorted(game.registry)}
    return entry


def copy_entry(entry: dict) -> dict:
    return {k: json.loads(json.dumps(entry[k])) for k in ("installDir", "files", "registry") if entry.get(k)}


def merge(into: dict, title: str, entry: dict):
    target = into.setdefault(title, {})
    for key in ("installDir", "files", "registry"):
        if entry.get(key):
            target.setdefault(key, {})
            for k, v in entry[key].items():
                target[key].setdefault(k, v)


def write_manifest(path: Path, entries: dict, header: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    # Sorted at every level so re-runs produce identical files (clean diffs).
    body = {
        t: {k: dict(sorted(e[k].items(), key=lambda i: i[0].lower())) for k in ("installDir", "files", "registry") if e.get(k)}
        for t, e in sorted(entries.items(), key=lambda i: i[0].lower())
    }
    body = {t: e for t, e in body.items() if e}
    lines = ["---"] + [f"# {line}" if line else "#" for line in header.splitlines()] + to_yaml(body)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------------------------
# Output: PCGamingWiki
# ---------------------------------------------------------------------------------------------

PCGW_PATHS = [
    ("<home>/AppData/LocalLow", "{{p|userprofile\\appdata\\locallow}}"),
    ("<winLocalAppData>", "{{p|localappdata}}"),
    ("<winAppData>", "{{p|appdata}}"),
    ("<winDocuments>", "{{p|userprofile\\documents}}"),
    ("<home>", "{{p|userprofile}}"),
    ("HKEY_CURRENT_USER", "{{p|hkcu}}"),
    ("HKEY_LOCAL_MACHINE", "{{p|hklm}}"),
]


def pcgw_path(path: str, game: Game | None) -> str:
    if path.startswith("<base>") or (game and game.base != "<base>" and path.startswith(game.base)):
        rest = path.split("/", 1)[1] if "/" in path else ""
        rest = re.sub(r"^(\*/)+", "", rest)  # wrapper folders are part of {{p|game}} on PCGW
        path = "{{p|game}}" + ("/" + rest if rest else "")
    else:
        for placeholder, token in PCGW_PATHS:
            if path.startswith(placeholder):
                path = token + path[len(placeholder):]
                break
    path = path.replace("/", "\\")
    return path.replace("\\*\\", "\\<company>\\") if "LocalLow" in path or "locallow" in path else path


def windows_paths(entry: dict) -> tuple[list, list]:
    files = []
    for p, info in (entry.get("files") or {}).items():
        oses = {w.get("os") for w in (info or {}).get("when") or [] if w.get("os")}
        if (not oses or "windows" in oses) and not p.startswith(("<xdg", "<home>/Library", "<home>/.")):
            files.append(p)
    return sorted(files, key=str.lower), sorted(entry.get("registry") or {})


def pcgw_date(iso: str) -> str:
    try:
        d = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return f"{d:%B} {d.day}, {d.year}"


def pcgw_game_data(game: Game, entry: dict) -> list:
    files, registry = windows_paths(entry)
    saves = "|".join(pcgw_path(p, game) for p in files)
    config = "|".join(pcgw_path(r, game) + "\\" for r in registry)
    return [
        "==Game data==",
        "===Configuration file(s) location===",
        "{{Game data|",
        f"{{{{Game data/config|Windows|{config}}}}}",
        "}}",
        "",
        "===Save game data location===",
        "{{Game data|",
        f"{{{{Game data/saves|Windows|{saves}}}}}",
        "}}",
    ]


def pcgw_stub(game: Game, entry: dict) -> str:
    engines = [
        f"{{{{Infobox game/row/engine|{name}" + (f"|build={build}" if build else "") + "}}"
        for name, build in game.engines.items()
    ] or ["<!-- engine unknown -->"]
    date = pcgw_date(game.published)
    monetization = "Freeware" if game.free else "One-time game purchase"
    return "\n".join([
        "{{stub}}",
        "{{Infobox game",
        "|cover        = ",
        "|developers   = ",
        f"{{{{Infobox game/row/developer|{game.creator}}}}} <!-- itch.io account name; use the studio name if different -->",
        "|publishers   = ",
        "|engines      = ",
        *engines,
        "|release dates= ",
        f"{{{{Infobox game/row/date|Windows|{date}}}}}",
        "|reception    = ",
        "|taxonomy     = ",
        f"{{{{Infobox game/row/taxonomy/monetization      | {monetization} }}}}",
        "{{Infobox game/row/taxonomy/microtransactions | None }}",
        "{{Infobox game/row/taxonomy/modes             | Singleplayer }}",
        "|steam appid  = ",
        "|gogcom id    = ",
        f"|official site= {game.url}",
        "|hltb         = ",
        "|igdb         = ",
        "|lutris       = ",
        "|mobygames    = ",
        "|strategywiki = ",
        "|wikipedia    = ",
        "|winehq       = ",
        f"|license      = {'freeware' if game.free else 'commercial'}",
        "}}",
        "",
        "{{Introduction",
        f"|introduction      = '''''{game.title}''''' is a game by {game.creator}, released on [[itch.io]].",
        "",
        f"|release history   = The game was released on itch.io on {date}." if date else "|release history   = ",
        "",
        "|current state     = ",
        "}}",
        "",
        "'''General information'''",
        f"{{{{mm}}}} [{game.url} itch.io page]",
        "",
        "==Availability==",
        "{{Availability|",
        f"{{{{Availability/row| itch.io | {game.url} | DRM-free |  |  | Windows }}}}",
        "}}",
        "",
        *pcgw_game_data(game, entry),
        "",
        "==System requirements==",
        "{{System requirements",
        "|OSfamily = Windows",
        "",
        "|minOS    = ",
        "|minCPU   = ",
        "|minRAM   = ",
        "|minHD    = ",
        "|minGPU   = ",
        "}}",
        "",
        "{{References}}",
        "",
    ])


def safe_filename(title: str) -> str:
    return re.sub(r'[<>:"/\\|?*]', "_", title).strip(" .")[:120]


# ---------------------------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", type=Path, default=APPDATA / "itch" / "db" / "butler.db", help="itch app database")
    ap.add_argument("--out", type=Path, default=HERE, help="output folder (default: this script's folder)")
    ap.add_argument("--ludusavi", help="path to ludusavi.exe (default: found on PATH / winget)")
    ap.add_argument("--no-prompt", action="store_true", help="don't ask; leave uncertain paths out for now")
    ap.add_argument("--fresh", action="store_true", help="don't merge with manifests already in --out")
    args = ap.parse_args()

    ludusavi = find_ludusavi(args.ludusavi)
    out = args.out
    decisions_file = out / "decisions.json"
    decisions = json.loads(decisions_file.read_text(encoding="utf-8")) if decisions_file.is_file() else {}

    print("Reading itch.io library...")
    games, skipped, locations = read_itch(args.db)

    print("Loading the official manifest...")
    official = ManifestIndex("official", dump_manifest(ludusavi, True, []))
    secondaries = []
    for s in user_secondaries(out):
        label = s.get("url") or s.get("path")
        print(f"Loading optional manifest {label} ...")
        try:
            secondaries.append(ManifestIndex(label, dump_manifest(ludusavi, False, [s])))
        except (subprocess.CalledProcessError, ValueError) as e:
            print(f"  skipped ({e})")

    print("Scanning save folders...")
    index = index_save_roots()

    interactive = not args.no_prompt and sys.stdin.isatty()
    results = []  # (game, source, manifest title, match how, entry)
    for game in games:
        match_save_folders(game, detect(game), index)
        for source in [official, *secondaries]:
            title, how = source.match(game)
            if title and same_game(game, title, how, source.data[title], decisions, interactive):
                results.append([game, source.name, title, how, source.data[title]])
                break
        else:
            results.append([game, "scraped", game.title, "", None])

    to_ask = [r[0] for r in results if r[1] == "scraped" or not has_windows_saves(r[4] or {})]
    pending = confirm(to_ask, decisions, prompt=interactive)
    out.mkdir(parents=True, exist_ok=True)
    decisions_file.write_text(json.dumps(decisions, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    complete, gapfill = {}, {}
    if not args.fresh:
        for name, target in zip(OUTPUT_MANIFESTS, (complete, gapfill)):
            existing = out / "manifests" / name
            if existing.is_file():
                for t, e in dump_manifest(ludusavi, False, [{"path": str(existing)}]).items():
                    # Ludusavi treats a local manifest as living in a game folder and adds that folder's
                    # name ("manifests") as an installDir; drop it.
                    (e.get("installDir") or {}).pop(existing.parent.name, None)
                    merge(target, t, e)

    pcgw_dir = out / "pcgw"
    pcgw_dir.mkdir(parents=True, exist_ok=True)
    report = []
    for game, source, title, how, entry in results:
        scraped = scraped_entry(game)
        if source == "scraped":
            merge(complete, title, scraped)
            merge(gapfill, title, scraped)
            final = scraped
        else:
            final = copy_entry(entry)
            itch_dir = {"installDir": {game.install_dir: {}}} if game.install_dir else {}
            merge(complete, title, final)
            merge(complete, title, itch_dir)
            needs_scrape = not has_windows_saves(entry)
            if source != "official":
                merge(gapfill, title, final)
            uses_base = any(p.startswith("<base>") for p in (entry.get("files") or {}))
            if itch_dir and (uses_base or needs_scrape or source != "official") and game.install_dir not in (entry.get("installDir") or {}):
                merge(gapfill, title, itch_dir)
            if needs_scrape:
                merge(complete, title, scraped)
                merge(gapfill, title, scraped)
                final = scraped

        if source != "official":
            (pcgw_dir / f"{safe_filename(game.title)}.wiki").write_text(pcgw_stub(game, final), encoding="utf-8")
        elif not has_windows_saves(entry) and (game.auto or game.registry):
            note = (f"<!-- For the existing PCGamingWiki page '{title}' (matched by {how}). Check it is the same game as "
                    f"{game.url} before adding, and add an itch.io row to its Availability table. -->")
            (pcgw_dir / f"{safe_filename(title)} (game data).wiki").write_text("\n".join([note, *pcgw_game_data(game, final)]) + "\n", encoding="utf-8")

        files, registry = windows_paths(final)
        report.append((game.title, source if source in ("official", "scraped") else "optional: " + source.rsplit("/", 1)[-1],
                       (f"{title} ({how})" if source != "scraped" else ""), ", ".join(game.engines) or "",
                       len(files) + len(registry), len(game.ask)))

    header = (
        "Ludusavi manifest for games from the itch.io desktop app. Generated by itch/scraper.py.\n"
        "Install-folder paths use <base>: add each itch install location as an \"Other\" root.\n"
        "Entries copied from the official manifest come from PCGamingWiki (CC BY-NC-SA 3.0)."
    )
    write_manifest(out / "manifests" / "itch-complete.yml", complete, header + "\nCOMPLETE: every known itch game. Use instead of itch-gapfill.yml, not with it.")
    write_manifest(out / "manifests" / "itch-gapfill.yml", gapfill, header + "\nGAP-FILL: only what the official manifest lacks. Use alongside the official manifest.")

    lines = [
        "# itch.io scrape report", "",
        f"{len(games)} installed itch games, {len(skipped)} skipped. Undecided paths: {pending}.", "",
        "| Game | Source | Matched entry | Engine | Windows save paths | Undecided |",
        "|------|--------|---------------|--------|-------------------:|----------:|",
    ]
    lines += [f"| {t} | {s} | {m} | {e} | {n} | {a} |" for t, s, m, e, n, a in report]
    lines += ["", "## Skipped", ""] + [f"- {t}: {why}" for t, why in skipped]
    (out / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    counts = {}
    for r in report:
        counts[r[1].split(":")[0]] = counts.get(r[1].split(":")[0], 0) + 1
    print(f"\n{len(games)} games: " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
    print(f"With Windows save paths: {sum(1 for r in report if r[4])}. Still undecided: {pending} paths (re-run without --no-prompt).")
    print(f"Wrote {out / 'manifests'}, {pcgw_dir}, {out / 'report.md'}")
    print("itch install locations (add each as an 'Other' root in Ludusavi): " + "; ".join(locations))


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    main()
