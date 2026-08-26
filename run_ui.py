#!/usr/bin/env python3
"""Launch the AuraScribe Gradio UI."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.main import init_system

if __name__ == "__main__":
    engine, scheduler, components = init_system()

    from src.ui import AppUI
    app = AppUI(engine, components.get("config") or {}, scheduler)

    print("Building Gradio app...", flush=True)
    gapp = app._build_gradio_app()
    print("Launching on http://127.0.0.1:7860 ...", flush=True)
    sys.stdout.flush()

    gapp.launch(
        server_name="127.0.0.1",
        server_port=7860,
        share=False,
        prevent_thread_lock=True,
    )

    import time
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...", flush=True)
