import argparse
import json
import os
import pathlib
import shutil
from typing import Any, Mapping, cast

from colorama import Fore, Style, init as colorama_init

from .codec import build_icon_kitchen_url, decode_url_fragment_to_json, encode_json_to_url_fragment
from .downloader import download_many_and_extract_sync
from .gitlab_uploader import upload_avatars_sync


def _load_json(path: pathlib.Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def _extract_json_from_url(url: str) -> None:
    """Extract and print JSON configuration from an icon.kitchen URL."""
    # Extract fragment from URL (part after /i/)
    if "/i/" not in url:
        raise SystemExit(f"Invalid icon.kitchen URL: expected '/i/' in URL: {url}")

    fragment = url.split("/i/", 1)[1]
    # Remove query string and fragment if present
    fragment = fragment.split("?")[0].split("#")[0]

    try:
        decoded = decode_url_fragment_to_json(fragment)
        print(json.dumps(decoded, indent=2, ensure_ascii=False))
    except Exception as exc:
        raise SystemExit(f"Failed to decode URL fragment: {exc}") from exc


def _deep_merge(base: Mapping[str, Any], override: Mapping[str, Any]) -> dict[str, Any]:
    """Recursively merge two mapping objects into a new dict.

    Values from ``override`` take precedence over values from ``base``.
    Nested dictionaries are merged recursively, everything else is replaced.
    """
    result: dict[str, Any] = dict(base)
    for key, value in override.items():
        if (
            key in result
            and isinstance(result[key], Mapping)
            and isinstance(value, Mapping)
        ):
            result[key] = _deep_merge(result[key], cast(Mapping[str, Any], value))
        else:
            result[key] = value
    return result


def main(argv: list[str] | None = None) -> None:
    colorama_init(autoreset=True)

    parser = argparse.ArgumentParser(
        prog="icon-kitchen-batch-export",
        description="Generate icon.kitchen URL from input.json and optionally download the ZIP.",
    )
    parser.add_argument(
        "input",
        type=pathlib.Path,
        nargs="?",
        help="Path to input.json with icon.kitchen configuration.",
    )
    parser.add_argument(
        "--extract-json",
        type=str,
        metavar="URL",
        help="Extract and print JSON configuration from an icon.kitchen URL.",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Open the URL in a headless browser, click Download and extract the ZIP.",
    )
    parser.add_argument(
        "--download-dir",
        type=pathlib.Path,
        default=pathlib.Path("downloads"),
        help="Directory for downloaded ZIP files (default: ./downloads).",
    )
    parser.add_argument(
        "--extract-dir",
        type=pathlib.Path,
        default=None,
        help="Directory to extract ZIP contents (default: <download-dir>/extracted).",
    )
    parser.add_argument(
        "--sub-extract",
        type=str,
        default=None,
        help=(
            "Relative path inside each extracted archive to additionally collect "
            "into <download-dir>/sub_extracted (for example: android/play_store_512.png)."
        ),
    )
    parser.add_argument(
        "--gitlab-uploader",
        action="store_true",
        help=(
            "After sub_extract, upload collected icons as GitLab project avatars. "
            "Requires GITLAB_TOKEN in environment and works only together with "
            "--download and --sub-extract."
        ),
    )

    args = parser.parse_args(argv)

    if args.extract_json:
        _extract_json_from_url(args.extract_json)
        return

    if args.input is None:
        raise SystemExit("Either 'input' path or '--extract-json URL' must be provided.")

    if args.gitlab_uploader and not args.sub_extract:
        raise SystemExit(
            "--gitlab-uploader can only be used together with --sub-extract."
        )

    if args.gitlab_uploader and not args.download:
        raise SystemExit(
            "--gitlab-uploader can only be used together with --download."
        )

    if args.gitlab_uploader and "GITLAB_TOKEN" not in os.environ:
        raise SystemExit(
            "Environment variable GITLAB_TOKEN must be set when using "
            "--gitlab-uploader."
        )

    data = _load_json(args.input)

    template_raw = data.get("template")
    items_raw = data.get("items")

    if not isinstance(template_raw, Mapping):
        raise SystemExit("input.json must contain a 'template' object.")
    if not isinstance(items_raw, list) or not items_raw:
        raise SystemExit("input.json must contain a non-empty 'items' array.")

    template = cast(Mapping[str, Any], template_raw)

    item_names: list[str] = []
    item_overrides: list[Mapping[str, Any]] = []

    for idx, raw_item in enumerate(cast(list[object], items_raw)):
        if not isinstance(raw_item, Mapping):
            raise SystemExit(
                f"items[{idx}] must be an object with overrides and a 'name'."
            )

        item = cast(Mapping[str, Any], raw_item)
        raw_name = item.get("name")
        if not isinstance(raw_name, str) or not raw_name.strip():
            raise SystemExit(
                f"items[{idx}] must contain a non-empty string field 'name'."
            )

        name = raw_name.strip()
        overrides_dict: dict[str, Any] = {
            key: value for key, value in item.items() if key != "name"
        }

        if not overrides_dict:
            raise SystemExit(f"items[{idx}] must contain overrides besides 'name'.")

        item_names.append(name)
        item_overrides.append(overrides_dict)

    urls: list[str] = []

    print(Fore.CYAN + "Icon.kitchen URLs:")

    for index, overrides in enumerate(item_overrides):
        merged = _deep_merge(template, overrides)
        fragment = encode_json_to_url_fragment(merged)
        url = build_icon_kitchen_url(fragment)
        urls.append(url)

        print(f"{Fore.YELLOW}[{index}]{Style.RESET_ALL} {url}")

    if args.download:
        _maybe_cleanup_previous_outputs(
            download_dir=args.download_dir,
            extract_dir=args.extract_dir,
            has_sub_extract=bool(args.sub_extract),
        )

        print(Fore.CYAN + "\nDownloading and extracting ZIP archives...")

        extracted_dirs = download_many_and_extract_sync(
            urls=urls,
            download_dir=args.download_dir,
            extract_dir=args.extract_dir,
            names=item_names,
        )
        for index, path in enumerate(extracted_dirs):
            print(f"{Fore.GREEN}[{index}] ZIP downloaded and extracted to: {path}")

        if args.sub_extract:
            _perform_sub_extract(
                extracted_dirs=extracted_dirs,
                item_names=item_names,
                download_dir=args.download_dir,
                relative_path=args.sub_extract,
            )
            if args.gitlab_uploader:
                _perform_gitlab_upload(
                    item_names=item_names,
                    download_dir=args.download_dir,
                    relative_path=args.sub_extract,
                )


def _maybe_cleanup_previous_outputs(
    download_dir: pathlib.Path,
    extract_dir: pathlib.Path | None,
    has_sub_extract: bool,
) -> None:
    base_extract_dir = extract_dir or (download_dir / "extracted")
    sub_extract_dir = download_dir / "sub_extracted"

    exists_extract = base_extract_dir.is_dir() and any(base_extract_dir.iterdir())
    exists_sub = (
        has_sub_extract and sub_extract_dir.is_dir() and any(sub_extract_dir.iterdir())
    )

    if not exists_extract and not exists_sub:
        return

    targets: list[pathlib.Path] = []
    if exists_extract:
        targets.append(base_extract_dir)
    if exists_sub:
        targets.append(sub_extract_dir)

    print(Fore.YELLOW + "Existing output directories detected:")
    for p in targets:
        print(f" - {p}")

    while True:
        answer = input(
            Fore.YELLOW + "Remove previous extracted data before continuing? [y/N]: "
        ).strip()
        if not answer:
            print(Fore.YELLOW + "Keeping existing data.")
            return
        if answer.lower() in {"y", "yes"}:
            break
        if answer.lower() in {"n", "no"}:
            print(Fore.YELLOW + "Keeping existing data.")
            return

    for p in targets:
        shutil.rmtree(p, ignore_errors=True)
        print(Fore.GREEN + f"Removed {p}")


def _perform_sub_extract(
    extracted_dirs: list[pathlib.Path],
    item_names: list[str],
    download_dir: pathlib.Path,
    relative_path: str,
) -> None:
    """Collect a single file from each extracted directory into sub_extracted/."""
    sub_dir = download_dir / "sub_extracted"
    sub_dir.mkdir(parents=True, exist_ok=True)

    rel_path = pathlib.Path(relative_path)

    print(Fore.CYAN + f"\nCollecting '{relative_path}' into {sub_dir}...")

    for index, (item_dir, name) in enumerate(zip(extracted_dirs, item_names)):
        source_path = item_dir / rel_path
        if not source_path.is_file():
            print(
                f"{Fore.RED}[{index}] Missing file for item '{name}': {source_path}",
            )
            continue

        target_path = sub_dir / f"{name}{source_path.suffix}"
        shutil.copy2(source_path, target_path)
        print(
            f"{Fore.GREEN}[{index}] Collected '{relative_path}' "
            f"from '{name}' to {target_path}"
        )


def _perform_gitlab_upload(
    item_names: list[str],
    download_dir: pathlib.Path,
    relative_path: str,
) -> None:
    """Upload collected sub_extracted icons as GitLab project avatars."""
    token = os.environ["GITLAB_TOKEN"]
    base_url = os.environ.get("GITLAB_BASE_URL", "https://gitlab.com")

    sub_dir = download_dir / "sub_extracted"
    suffix = pathlib.Path(relative_path).suffix

    avatars: dict[str, pathlib.Path] = {}
    print(Fore.CYAN + "\nUploading collected icons to GitLab projects...")

    for name in item_names:
        avatar_path = sub_dir / f"{name}{suffix}"
        if not avatar_path.is_file():
            print(
                Fore.YELLOW
                + f"[gitlab] Skipping '{name}': avatar file not found at {avatar_path}"
            )
            continue
        avatars[name] = avatar_path

    upload_avatars_sync(token=token, avatars=avatars, base_url=base_url)


if __name__ == "__main__":
    main()
