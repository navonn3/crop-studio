# Crop Studio

Password-protected browser tool for keyframed reframing (default 9:16) of a local video, using the MediaHub vcrop model:
IN/OUT trim + crop-center keyframes with linear interpolation, then MP4 export in the browser (Mediabunny / WebCodecs).
The video is never uploaded.

- `src/app.html` holds the plaintext app. It is git-ignored and kept locally only.
- `src/gate.html` is the password page.
- `build.mjs` encrypts the app into `docs/index.html` (AES-GCM, PBKDF2 key).

Rebuild: `CROP_PASSWORD='…' node build.mjs`, then commit `docs/` and push.
