# Third-party software, models and assets

Said vs. Shown is MIT-licensed. It uses the following. **Bundled** means it ships in this repository. **Fetched** means setup downloads it onto your machine; it is not redistributed here.

| Component | How it's used | License | Notes |
|---|---|---|---|
| [HyperFrames](https://github.com/heygen-com/hyperframes) CLI + skills (HeyGen) | Fetched via `npx`; renders HTML to video | Apache-2.0 | Anonymous telemetry is on by default; disable with `npx hyperframes telemetry disable` or `HYPERFRAMES_NO_TELEMETRY=1` |
| [GSAP](https://gsap.com) | Animation runtime, loaded by compositions | GSAP Standard "no charge" license | Free to use; not an OSI license. See https://gsap.com/standard-license/ |
| [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) | Fetched; local text-to-speech model | Apache-2.0 | |
| [kokoro-onnx](https://github.com/thewh1teagle/kokoro-onnx) | Fetched into a local venv | MIT | Pulls in phonemizer and espeak-ng (GPL-3.0+). They are installed on your machine by setup, never bundled here |
| [Parakeet TDT 0.6B v3](https://huggingface.co/nvidia/parakeet-tdt-0.6b-v3) (NVIDIA) | Optional; fetched; local speech recognition | CC-BY-4.0 | Attribution: NVIDIA. The fallback is whisper.cpp small.en (MIT) |
| [puppeteer-core](https://github.com/puppeteer/puppeteer), [@puppeteer/browsers](https://github.com/puppeteer/puppeteer) | Fetched; captures source pages | Apache-2.0 | Chrome / chrome-headless-shell is downloaded under Google's terms |
| [Newsreader](https://github.com/productiontype/Newsreader) (Production Type) | Bundled woff2 in `templates/fonts/` | SIL OFL 1.1 | License text alongside the files |
| [IBM Plex Mono](https://github.com/IBM/plex) (IBM) | Bundled; IBM's own split woff2 in `templates/fonts/` | SIL OFL 1.1, Reserved Font Name "Plex" | Unmodified IBM files; license text alongside |
| Sound marks (`templates/sfx/*.wav`) | Bundled | MIT (this repo) | Synthesized with ffmpeg; the commands are in `templates/sfx/SFX.md` |

Source captures (screenshots, page text) are made on your machine at build time from pages you choose. They are git-ignored and never redistributed by this project.
