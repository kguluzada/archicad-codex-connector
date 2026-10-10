"""Build and check the Windows setup ZIP from explicit deliverable paths."""

import hashlib
import shutil
import tomllib
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

ROOT = Path(__file__).resolve().parents[1]
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["version"]
DIST = ROOT / "dist"
WHEEL = DIST / f"archicad_codex_connector-{VERSION}-py3-none-any.whl"
SOURCE = DIST / f"archicad_codex_connector-{VERSION}.tar.gz"
BUNDLE = DIST / f"archicad-connector-{VERSION}-windows.zip"
PREFIX = "archicad-connector/"


def main():
    for artifact in (WHEEL, SOURCE):
        if not artifact.is_file():
            raise FileNotFoundError(f"Build Python artifacts first: {artifact.name}")
    paths = [ROOT / name for name in ("README.md", "LICENSE", "pyproject.toml", "uv.lock", ".gitignore")]
    for folder in ("src", "scripts", "tests", "examples", "docs"):
        paths.extend(
            path
            for path in (ROOT / folder).rglob("*")
            if path.is_file()
            and not any(
                part.startswith(".") or part == "__pycache__" for part in path.relative_to(ROOT).parts
            )
        )
    members = [(path, PREFIX + path.relative_to(ROOT).as_posix()) for path in sorted(paths)]
    members.append((WHEEL, PREFIX + "packages/" + WHEEL.name))
    with ZipFile(BUNDLE, "w", compression=ZIP_DEFLATED) as archive:
        for path, name in members:
            if path.is_symlink():
                raise ValueError(f"Refusing symlink: {path}")
            info = ZipInfo(name, date_time=(2026, 10, 10, 0, 0, 0))
            info.compress_type = ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    with ZipFile(BUNDLE) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(set(archive.namelist())) == len(members)
        for path, name in members:
            assert archive.read(name) == path.read_bytes(), name
        for required in ("scripts/setup.ps1", "uv.lock", "src/archicad_connector/data/TAPIR_LICENSE.txt"):
            assert PREFIX + required in archive.namelist()
        assert not any(
            "/.env" in name or "__pycache__" in name or ".." in name.split("/") for name in archive.namelist()
        )
    checksums = "".join(
        f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in (BUNDLE, WHEEL, SOURCE)
    )
    (DIST / "SHA256SUMS").write_text(checksums)
    downloads = ROOT / "site/private"
    downloads.mkdir(parents=True, exist_ok=True)
    for path in (BUNDLE, WHEEL, SOURCE, DIST / "SHA256SUMS"):
        shutil.copyfile(path, downloads / path.name)
    print(f"Checked {len(members)} ZIP members; copied 4 release files to site/private")


if __name__ == "__main__":
    main()
