from __future__ import annotations

import asyncio
import pathlib
import zipfile
from typing import Optional

from playwright.async_api import async_playwright


DOWNLOAD_BUTTON_SELECTOR = 'button[aria-label="Download"]'


async def download_many_and_extract(
    urls: list[str],
    download_dir: pathlib.Path,
    extract_dir: Optional[pathlib.Path] = None,
    names: Optional[list[str]] = None,
) -> list[pathlib.Path]:
    """Download and extract multiple ZIPs using a single browser instance.

    Each URL will be opened, its ZIP downloaded into ``download_dir``, extracted into
    ``extract_dir/<name>`` (or ``extract_dir/item_<index>`` if names are not provided),
    and then the ZIP file will be removed.
    """
    if names is not None and len(names) != len(urls):
        raise ValueError("Length of 'names' must match length of 'urls'.")

    download_dir.mkdir(parents=True, exist_ok=True)
    base_extract_dir = extract_dir or (download_dir / "extracted")
    base_extract_dir.mkdir(parents=True, exist_ok=True)

    extracted_dirs: list[pathlib.Path] = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            channel="chromium-headless-shell", headless=True
        )
        context = await browser.new_context(accept_downloads=True)
        page = await context.new_page()

        for index, url in enumerate(urls):
            await page.goto(url, wait_until="networkidle")

            async with page.expect_download() as download_info:
                await page.click(DOWNLOAD_BUTTON_SELECTOR)

            download = await download_info.value
            filename = download.suggested_filename or f"icon-kitchen-{index}.zip"
            zip_path = download_dir / filename
            await download.save_as(str(zip_path))

            folder_name = names[index] if names is not None else f"item_{index}"
            target_dir = base_extract_dir / folder_name
            target_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(target_dir)

            try:
                zip_path.unlink()
            except OSError:
                pass

            extracted_dirs.append(target_dir)

        await context.close()
        await browser.close()

    return extracted_dirs


def download_many_and_extract_sync(
    urls: list[str],
    download_dir: pathlib.Path,
    extract_dir: Optional[pathlib.Path] = None,
    names: Optional[list[str]] = None,
) -> list[pathlib.Path]:
    """Synchronous wrapper around ``download_many_and_extract``."""
    return asyncio.run(download_many_and_extract(urls, download_dir, extract_dir, names))
