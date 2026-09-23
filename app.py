import gradio as gr
import bm_app2

# Build the Gradio application
demo, _ = bm_app2.build_app()

# Vercel's Python runtime needs a top-level WSGI/ASGI-compatible app.
# Gradio exposes the underlying application through demo.app.
app = demo.app
