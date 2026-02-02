.PHONY: install playwright-install run run-download run-sub-extract run-gitlab-uploader extract-json

install:
	poetry install

playwright-install:
	poetry run playwright install chromium-headless-shell

run:
	poetry run icon-kitchen-gitlab-sync input.json

run-download:
	poetry run icon-kitchen-gitlab-sync input.json --download

run-sub-extract:
	poetry run icon-kitchen-gitlab-sync input.json --download \
	  --sub-extract android/play_store_512.png

run-gitlab-uploader:
	@if [ -f .env ]; then set -a; . ./.env; set +a; fi; \
	poetry run icon-kitchen-gitlab-sync input.json --download \
	  --sub-extract android/play_store_512.png \
	  --gitlab-uploader

extract-json:
	@URL="$(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))"; \
	if [ -z "$$URL" ]; then \
		echo "Usage: make extract-json <icon.kitchen URL>"; \
		exit 1; \
	fi; \
	poetry run icon-kitchen-gitlab-sync --extract-json "$$URL"

%:
	@: