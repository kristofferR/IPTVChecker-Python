# Repository Guidelines

## Project Overview
IPTV Stream Checker is a Python CLI that inspects IPTV M3U/M3U8 playlists, confirms stream availability, captures screenshots, and annotates channels with codec, resolution, and audio metadata. It highlights dead or geoblocked entries, detects mislabeled streams, and can split playlists into working, dead, and geoblocked variants.

## Project Structure & Module Organization
The codebase revolves around `IPTV_checker.py`, which orchestrates playlist parsing, stream validation, media inspection, and reporting. Keep supplemental modules either in the repo root or a `utils/` package if single-file maintenance becomes unwieldy. Sample playlists (`test_playlist.m3u`, `MEGAOTT.m3u`, `DATOO.m3u`) support deterministic testing—avoid modifying them in commits. Generated artifacts (renamed playlists, screenshots, split outputs) are emitted alongside the source playlist and should stay untracked.

## Core Architecture
- `check_channel_status` handles HTTP checks, follows nested HLS playlists, and validates media segments before optional `ffmpeg` probes.
- `parse_m3u8_file` coordinates resume logic, status logging, optional splitting/renaming, and screenshot capture.
- `get_stream_info` / `get_audio_bitrate` wrap `ffprobe` for codec, resolution, FPS, and audio bitrate details.
- `capture_frame` extracts reference images; failures should not abort processing.
- Console output uses terminal-width detection for padding and color-coded status glyphs.

## Build, Test, and Development Commands
- `python3 -m venv .venv && source .venv/bin/activate`: create a virtual environment (Python 3.10+ recommended).
- `pip install -r requirements.txt`: installs `requests`, `ffmpeg-python`, and `PySocks`.
- `python IPTV_checker.py test_playlist.m3u -vv`: exercise verbose logging, playlist traversal, and screenshot paths.
- `python IPTV_checker.py --help`: verify new CLI switches render correctly after edits.

## Coding Style & Naming Conventions
Use four-space indentation, snake_case for functions, and descriptive constants. Keep logging through `logging` (INFO/DEBUG) rather than `print`, except for the ASCII banner. When you introduce CLI flags, supply both short and long forms and document them in `README.md`.

## Testing Guidelines
No automated suite exists; rely on manual validation with the bundled sample and at least one live provider list. Confirm alive/dead/geoblocked tallies, inspect generated playlists, and compare screenshots when visual regressions matter. For proxy flows, run with `-proxy-list` and `-test-geoblock` to cover both code paths and capture expected log output in PR notes.

## Commit & Pull Request Guidelines
Follow the repo’s pattern of concise, imperative subjects (e.g., “Improve proxy retry jitter”). Keep commits scoped; include body context when touching network timeouts or ffmpeg interactions. Pull requests should link motivating issues, enumerate manual test commands, and mention new CLI options or documentation updates.

## Generated Artifacts & Logs
Expect directories such as `{playlist}_{group}_screenshots/` and logs `{playlist}_{group}_checklog.txt` for resume support. With `-split`, the tool writes `{playlist}_working.m3u8`, `{playlist}_dead.m3u8`, and geoblocked variants; guard against committing these outputs.

## Security & Configuration Tips
Never commit real playlists, credentials, or proxy lists—use sanitized fixtures. Ensure `ffmpeg`/`ffprobe` binaries are installed and callable before enabling screenshot or metadata features. Keep the default `User-Agent` unless contracts require otherwise, and note any changes in review. Apply subprocess timeouts consistently to avoid hung checks in CI or unattended runs.
