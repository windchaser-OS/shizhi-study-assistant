"""Release asset allowlist shared by the spec and distribution verifier.

Never collect the project directory recursively. User vaults, databases, API
profiles, uploads, .env files and other machine-specific files are not assets.
"""
from pathlib import Path


WEB_FILES = (
    "index.html", "app.js", "styles.css", "readability.css", "favicon.svg",
    "vendor/katex/katex.min.js", "vendor/katex/katex.min.css",
    "vendor/katex/contrib/auto-render.min.js", "vendor/katex/LICENSE",
)
FONT_STEMS = (
    "AMS-Regular", "Caligraphic-Bold", "Caligraphic-Regular",
    "Fraktur-Bold", "Fraktur-Regular", "Main-Bold", "Main-BoldItalic",
    "Main-Italic", "Main-Regular", "Math-BoldItalic", "Math-Italic",
    "SansSerif-Bold", "SansSerif-Italic", "SansSerif-Regular",
    "Script-Regular", "Size1-Regular", "Size2-Regular", "Size3-Regular",
    "Size4-Regular", "Typewriter-Regular",
)
WEB_FILES += tuple(
    f"vendor/katex/fonts/KaTeX_{stem}.{extension}"
    for stem in FONT_STEMS for extension in ("ttf", "woff", "woff2")
)
GENERATED_LICENSES = (
    "Python-LICENSE.txt", "pypdf-LICENSE.txt", "PyInstaller-COPYING.txt",
    "Tcl-LICENSE.txt", "Tk-LICENSE.txt", "OpenSSL-LICENSE.txt",
    "KaTeX-LICENSE.txt", "Expat-LICENSE.txt", "zlib-LICENSE.txt",
)


def checked_file(root: Path, relative: str) -> Path:
    source = root / relative
    resolved = source.resolve(strict=True)
    if not resolved.is_relative_to(root.resolve()) or source.is_symlink():
        raise ValueError(f"Asset escapes its allowed root: {relative}")
    if not resolved.is_file():
        raise ValueError(f"Not a release file: {relative}")
    return resolved


def collect_assets(root: Path) -> list[tuple[str, str]]:
    assets = [
        (str(checked_file(root, f"web/{relative}")), str(Path("web") / Path(relative).parent))
        for relative in WEB_FILES
    ]
    assets += [(str(checked_file(root, "THIRD_PARTY_NOTICES.md")), ".")]
    generated = root / "build/windows/generated"
    assets += [(str(checked_file(generated, filename)), ".")
               for filename in ("build-info.json", "app.ico")]
    assets += [
        (str(checked_file(generated, f"licenses/{filename}")), "licenses")
        for filename in GENERATED_LICENSES
    ]
    return assets
