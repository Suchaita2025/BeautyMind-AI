---
title: BeautyMindAI
emoji: 💆‍♀️
colorFrom: pink
colorTo: purple
sdk: gradio
app_file: app.py
pinned: false
---

# BeautyMindAI

This folder is a ready-to-deploy Hugging Face Space.

## What's included
- `app.py` — entry point Spaces will run (`bm_app2.build_app()` + `launch()`)
- `bm_config.py`, `bm_ml.py`, `bm_alerts.py`, `bm_rules.py`, `bm_skin.py`,
  `bm_routine.py` (patched with the recommend-fill logic), `bm_dash.py`,
  `bm_app.py`, `bm_app2.py`, `bm_recommend.py`
- `models/` — your trained models (`shelf_models.pkl`, `skin_type.keras`,
  `skin_acne.keras`, and their class-label JSON files)
- `db/beautymind.db` — your existing users/products database
- `requirements.txt`

All Google Drive / Colab paths have been replaced with a local path
(`bm_config.py`'s `BASE` is now just the folder the code lives in), so
everything reads `models/` and `db/` right next to the code — no Drive
mount needed.

## Deploy steps

1. **Create the Space**: go to huggingface.co → your profile → "New Space".
   Name it (e.g. `beautymind-ai`), SDK = **Gradio**, hardware = CPU basic
   (free) to start.

2. **Upload these files**: easiest is drag-and-drop through the Space's
   "Files" tab — upload every file and folder in this package, keeping the
   `models/` and `db/` subfolders intact. (Or clone the Space repo with git,
   copy these files in, `git add . && git commit -m "deploy" && git push`.)

   Note: `models/shelf_models.pkl` and the two `.keras` files are fairly
   large (tens of MB). If the web uploader struggles, use git — Hugging Face
   Spaces repos handle large files fine (Git LFS kicks in automatically for
   big binaries).

3. **Wait for the build**: the Space installs `requirements.txt` and starts
   `app.py` automatically. Check the "Logs" tab if it fails to start —
   most likely culprit is a version mismatch (see below).

4. **Your permanent link**: once it's live, it's at
   `https://huggingface.co/spaces/<your-username>/beautymind-ai` — no Colab,
   no expiry.

## If something breaks on first boot

- **TensorFlow/Keras version mismatch**: your notebook used TF 2.20 to save
  the `.keras` models. If the Space's `tensorflow-cpu` resolves to a very
  different version and refuses to load them, pin it in `requirements.txt`,
  e.g. `tensorflow-cpu==2.20.0`.
- **mediapipe / opencv build issues on CPU-only Spaces**: if the build fails
  on these, check the Logs tab for the exact error — sometimes an older
  mediapipe wheel is needed for certain Python versions Spaces uses.
- **Free CPU tier is slow** for the CNN skin-analysis inference. If it's too
  slow for real use, you can upgrade the Space's hardware tier (paid) later
  without changing any code.
