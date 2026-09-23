"""
Entry point for BeautyMindAI.
Works for Hugging Face Spaces (Gradio SDK auto-runs app.py) and for
Render.com / any host that assigns a port via the $PORT env var.
"""
import os
import bm_app2

demo, lk = bm_app2.build_app()

# Render (and most free hosts) require binding to 0.0.0.0 on the port
# they provide via the PORT environment variable. Hugging Face Spaces
# doesn't set PORT, so this falls back to Gradio's own default there.
lk["server_name"] = "0.0.0.0"
lk["server_port"] = int(os.environ.get("PORT", 7860))

demo.launch(**lk)
