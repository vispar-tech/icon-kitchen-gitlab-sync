from __future__ import annotations

import asyncio
import pathlib
from typing import Any, Mapping, cast

import aiohttp
from aiohttp import ClientResponseError, ClientSession
from colorama import Fore

import io
from PIL import Image

MAX_AVATAR_SIZE = 200 * 1024  # 200 KB


def compress_image_to_size(
    path: pathlib.Path, max_size: int = MAX_AVATAR_SIZE
) -> tuple[io.BytesIO, str]:
    """
    Open image from path, compress to <= max_size bytes, return (BytesIO, content_type).
    If image is already small enough, returns original (or converted if PNG and user requests JPEG).
    Always outputs PNG or JPEG depending on file extension.
    """
    img = Image.open(path)
    ext = path.suffix.lower()
    output_format = "PNG"
    content_type = "image/png"
    params: dict[str, Any] = {}
    # If extension indicates JPEG, prefer JPEG
    if ext in {".jpg", ".jpeg"}:
        img = img.convert("RGB")
        output_format = "JPEG"
        content_type = "image/jpeg"
        params = {"optimize": True, "quality": 85}
    else:
        # Optimize PNG, let Pillow choose best parameters
        params = {"optimize": True}

    # Start at best quality, decrease if needed
    step_quality = [100, 95, 90, 85, 80, 70, 60, 50, 40, 30, 10]
    save_kwargs: dict[str, Any] = {}
    buffer = io.BytesIO()
    for q in step_quality:
        buffer.seek(0)
        buffer.truncate(0)
        save_kwargs = params.copy()
        if output_format == "JPEG":
            save_kwargs["quality"] = q
        img.save(buffer, format=output_format, **save_kwargs)
        if buffer.tell() <= max_size:
            break
    else:
        # last-ditch: try to resize if still too large
        width, height = img.size
        while buffer.tell() > max_size and width > 128 and height > 128:
            width = int(width * 0.9)
            height = int(height * 0.9)
            img_resized = img.resize((width, height), resample=Image.Resampling.LANCZOS)  # type: ignore
            buffer.seek(0)
            buffer.truncate(0)
            img_resized.save(buffer, format=output_format, **save_kwargs)
            if buffer.tell() <= max_size:
                break
        # Fallback: if still too big, just use the current result (could still be oversized)
    buffer.seek(0)
    return buffer, content_type


async def _find_project_id(
    session: ClientSession,
    project_name: str,
) -> int | None:
    """Return the project id that matches ``project_name``.

    If multiple projects share this name, the user is asked to choose one.
    """
    params = {
        "search": project_name,
        "simple": "true",
        "membership": "true",
    }

    try:
        async with session.get("/api/v4/projects", params=params) as resp:
            resp.raise_for_status()

            try:
                data = await resp.json()
            except Exception as exc:
                print(
                    Fore.RED
                    + f"[gitlab] Invalid JSON while searching for '{project_name}': {exc}"
                )
                return None

            if not isinstance(data, list):
                print(
                    Fore.RED
                    + f"[gitlab] Unexpected JSON payload while searching for '{project_name}': "
                    f"expected list, got {type(data).__name__}"
                )
                return None
            data = cast("list[dict[str, Any]]", data)
    except ClientResponseError as exc:
        print(
            Fore.RED + f"[gitlab] Failed to search project '{project_name}': "
            f"HTTP {exc.status} - {exc.message}"
        )
        return None

    exact_matches: list[dict[str, object]] = []
    for proj in data:
        if proj.get("name") == project_name:
            exact_matches.append(proj)

    if not exact_matches:
        print(
            Fore.RED
            + f"[gitlab] No exact project match found for name '{project_name}'."
        )
        return None

    if len(exact_matches) == 1:
        proj_id = exact_matches[0].get("id")
        if isinstance(proj_id, int):
            return proj_id
        print(
            Fore.RED
            + f"[gitlab] Project '{project_name}' has invalid 'id' field: {proj_id!r}"
        )
        return None

    print(Fore.YELLOW + f"[gitlab] Multiple projects found for name '{project_name}':")
    for idx, proj in enumerate(exact_matches):
        pid = proj.get("id")
        path_with_namespace = proj.get("path_with_namespace", "unknown")
        print(f"  [{idx}] id={pid} path={path_with_namespace}")

    while True:
        choice = input(
            Fore.YELLOW + f"Select project index for '{project_name}' (empty to skip): "
        ).strip()
        if not choice:
            print(
                Fore.YELLOW
                + f"[gitlab] Skipping upload for '{project_name}' (no selection)."
            )
            return None
        if not choice.isdigit():
            print(Fore.RED + "Please enter a valid number or press Enter to skip.")
            continue

        idx = int(choice)
        if not (0 <= idx < len(exact_matches)):
            print(
                Fore.RED
                + f"Please enter a number between 0 and {len(exact_matches)-1}."
            )
            continue

        selected = exact_matches[idx]
        proj_id = selected.get("id")
        if isinstance(proj_id, int):
            return proj_id

        print(
            Fore.RED + f"[gitlab] Selected project has invalid 'id' field: {proj_id!r}"
        )
        return None


async def _upload_single_avatar(
    session: ClientSession,
    project_name: str,
    avatar_path: pathlib.Path,
) -> None:
    proj_id = await _find_project_id(session, project_name)
    if proj_id is None:
        return

    if not avatar_path.is_file():
        print(
            Fore.RED
            + f"[gitlab] Avatar file for '{project_name}' not found: {avatar_path}"
        )
        return

    # --- Compress image to fit size limit ---
    try:
        buffer, content_type = compress_image_to_size(avatar_path, MAX_AVATAR_SIZE)
        buffer_len = buffer.getbuffer().nbytes
        if buffer_len > MAX_AVATAR_SIZE:
            print(
                Fore.YELLOW
                + f"[gitlab] Warning: Avatar for '{project_name}' is still {buffer_len/1024:.1f} KB after compression"
            )
    except Exception as exc:
        print(
            Fore.RED + f"[gitlab] Failed to compress avatar for '{project_name}': {exc}"
        )
        return

    form = aiohttp.FormData()
    form.add_field(
        "avatar",
        buffer,
        filename=avatar_path.name,
        content_type=content_type,
    )

    async with session.put(f"/api/v4/projects/{proj_id}", data=form) as resp:
        body = await resp.text()
        if 200 <= resp.status < 300:
            print(
                Fore.GREEN + f"[gitlab] Updated avatar for '{project_name}' "
                f"(id={proj_id}) from {avatar_path} ({buffer_len//1024} KB)"
            )
        else:
            print(
                Fore.RED + f"[gitlab] Failed to update avatar for '{project_name}' "
                f"(id={proj_id}): HTTP {resp.status}\nFull response:\n{body}"
            )


async def _upload_avatars(
    token: str,
    base_url: str,
    avatars: Mapping[str, pathlib.Path],
) -> None:
    if not avatars:
        print(Fore.RED + "[gitlab] No avatars to upload.")
        return

    timeout = aiohttp.ClientTimeout(total=60)
    base = base_url.rstrip("/")

    async with aiohttp.ClientSession(
        base_url=base,
        timeout=timeout,
        headers={"PRIVATE-TOKEN": token},
    ) as session:
        for name, path in avatars.items():
            await _upload_single_avatar(session, name, path)


def upload_avatars_sync(
    token: str,
    avatars: Mapping[str, pathlib.Path],
    base_url: str = "https://gitlab.com",
) -> None:
    """Synchronous wrapper that uploads avatars for multiple projects.

    ``avatars`` is a mapping of ``project_name`` -> ``avatar_path``.
    """
    asyncio.run(_upload_avatars(token=token, base_url=base_url, avatars=avatars))
