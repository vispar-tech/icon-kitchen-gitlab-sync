## icon-kitchen-gitlab-sync

Generate icon.kitchen URLs, download icons, and sync them as GitLab project avatars.

### Install

```bash
poetry install
poetry run playwright install chromium-headless-shell
```

### Quick start: GitLab avatar sync

- **Environment**

  - `GITLAB_TOKEN` – personal access token with API access.
  - Optional: `GITLAB_BASE_URL` – your GitLab URL (default: `https://gitlab.com`).
  - Each `items[*].name` in `input.json` must match a GitLab project name.

- **Run full pipeline (make target, uses `.env` if present)**:

```bash
make run-gitlab-uploader
```

- **Equivalent raw CLI command**:

```bash
export GITLAB_TOKEN="glpat-..."
# export GITLAB_BASE_URL="https://gitlab.example.com"  # optional

poetry run icon-kitchen-gitlab-sync input.json --download \
  --sub-extract android/play_store_512.png \
  --gitlab-uploader
```

For each item:

- The collected file `downloads/sub_extracted/<name>.png` (or `.jpg`) is used as the avatar.
- Projects are searched by name; if several exact matches are found, you will choose one in the terminal.

### Basic usage (without GitLab)

Generate URLs only:

```bash
poetry run icon-kitchen-gitlab-sync input.json
```

Generate URLs and download/extract all archives:

```bash
poetry run icon-kitchen-gitlab-sync input.json --download
```

Additionally collect a specific file (for example `android/play_store_512.png`)
from each archive into `downloads/sub_extracted/`:

```bash
poetry run icon-kitchen-gitlab-sync input.json --download \
  --sub-extract android/play_store_512.png
```

### `input.json` format (template + items)

Each item must have a `name`; it becomes the folder name under `downloads/extracted/`
and the base name for optional sub-extracted files.

```json
{
	"template": {
		"values": {
			"fgColor": "#ffffff",
			"bgColor": "#6a3de8"
		},
		"modules": ["ios", "android"]
	},
	"items": [
		{
			"name": "blue-solid",
			"values": {
				"bgColor": "#6a3de8"
			}
		},
		{
			"name": "pink-solid",
			"values": {
				"bgColor": "#ff4081"
			}
		}
	]
}
```
