# Legacy baseline

Captured before modernization from upstream commit `4a3b5fab50a55950d72a8145b8a11992ebbd7030` (`Add example Home Assistant YAML`, 2020-10-10).

- License: MIT, copyright Adam Thole (2019).
- Entry point: `PyPotter.py`, invoked with seven positional/optional values: video source, Home Assistant URL, API token, background removal, output windows, training mode, and FPS debugging.
- Importable helpers: `HassApi.HassApi` for Home Assistant REST calls and `CountsPerSec.CountsPerSec` for FPS measurements.
- Runtime imports: OpenCV, NumPy, Requests; no dependency manifest or lockfile existed.
- Persistence: none; the `Training/` directory is an image corpus organized by label. The legacy process trains an OpenCV KNN classifier, reads a camera/video stream, and triggers `automation.wand_<spell>` in Home Assistant.
- External assumptions: camera/video source, OpenCV GUI windows unless disabled, and a reachable Home Assistant instance with a bearer token.
- Test baseline: no tests were present. The no-argument command prints `Incorrect number of arguments. Required Arguments: [video source url] [home assistant URL] [API token]` and exits successfully.

The original root modules and training corpus remain in place. The v2 web path adds SQLite history without rewriting those files.

