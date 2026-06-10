"""PDF to Markdown converter — Shiny for Python frontend around the LiteParse CLI.

Run with:  shiny run app.py
"""

import io
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path

from shiny import App, reactive, render, ui

DEFAULT_OUTPUT_DIR = Path.home() / "markdown_output"

app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.input_file(
            "pdfs",
            "Select PDF files",
            accept=[".pdf"],
            multiple=True,
            button_label="Browse…",
            placeholder="No files selected",
        ),
        ui.input_text(
            "output_dir",
            "Local output folder",
            value=str(DEFAULT_OUTPUT_DIR),
        ),
        ui.input_action_button("convert", "Convert to Markdown", class_="btn-primary"),
        ui.hr(),
        ui.download_button("download_zip", "Download ZIP"),
        width=350,
    ),
    ui.card(
        ui.card_header("Conversion results"),
        ui.output_ui("status"),
        ui.output_table("results_table"),
    ),
    title="PDF → Markdown (LiteParse)",
)


def convert_pdf(pdf_path: Path, output_dir: Path) -> Path:
    """Convert one PDF to Markdown with the LiteParse CLI. Returns the .md path."""
    txt_output = output_dir / f"{pdf_path.stem}.txt"
    subprocess.run(
        ["lit", "parse", str(pdf_path), "--format", "text", "-o", str(txt_output)],
        check=True,
        capture_output=True,
        text=True,
    )
    md_output = output_dir / f"{pdf_path.stem}.md"
    txt_output.replace(md_output)
    return md_output


def server(input, output, session):
    results = reactive.value([])  # list of dicts: file, status, output
    converted_files = reactive.value([])  # list of Path to .md files

    @reactive.effect
    @reactive.event(input.convert)
    def _():
        file_infos = input.pdfs()
        if not file_infos:
            ui.notification_show("Please select at least one PDF first.", type="warning")
            return

        output_dir = Path(input.output_dir()).expanduser()
        try:
            output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            ui.notification_show(f"Cannot create output folder: {e}", type="error")
            return

        rows = []
        md_files = []
        with ui.Progress(min=0, max=len(file_infos)) as progress:
            with tempfile.TemporaryDirectory() as tmp:
                for i, f in enumerate(file_infos):
                    name = f["name"]
                    progress.set(i, message=f"Converting {name}…")

                    # LiteParse detects the format from the extension, so give
                    # the uploaded temp file back its original name.
                    pdf_path = Path(tmp) / name
                    shutil.copy(f["datapath"], pdf_path)

                    try:
                        md_path = convert_pdf(pdf_path, output_dir)
                        md_files.append(md_path)
                        rows.append({"File": name, "Status": "✅ Converted", "Output": str(md_path)})
                    except subprocess.CalledProcessError as e:
                        detail = (e.stderr or e.stdout or "").strip().splitlines()
                        rows.append({
                            "File": name,
                            "Status": "❌ Failed",
                            "Output": detail[-1] if detail else "LiteParse error",
                        })
            progress.set(len(file_infos), message="Done")

        results.set(rows)
        converted_files.set(md_files)
        n_ok = len(md_files)
        ui.notification_show(
            f"Converted {n_ok} of {len(file_infos)} file(s) into {output_dir}",
            type="message" if n_ok == len(file_infos) else "warning",
        )

    @render.ui
    def status():
        if not results():
            return ui.p(
                "Select one or more PDFs, choose where to save the Markdown files, "
                "then click “Convert to Markdown”.",
                class_="text-muted",
            )
        n_ok = sum(1 for r in results() if r["Status"].startswith("✅"))
        return ui.p(f"{n_ok} of {len(results())} file(s) converted successfully.")

    @render.table
    def results_table():
        import pandas as pd

        if not results():
            return None
        return pd.DataFrame(results())

    @session.download(
        filename=lambda: f"markdown_files_{datetime.now():%Y%m%d_%H%M%S}.zip"
    )
    def download_zip():
        files = [p for p in converted_files() if p.exists()]
        if not files:
            ui.notification_show("Nothing to download — run a conversion first.", type="warning")
            return
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zipf:
            for md in files:
                zipf.write(md, arcname=md.name)
        buf.seek(0)
        yield buf.read()


app = App(app_ui, server)
