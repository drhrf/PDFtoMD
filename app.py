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
PREVIEW_CHAR_LIMIT = 200_000

DROPZONE_CSS = """
.dropzone {
    border: 2px dashed var(--bs-border-color, #ccc);
    border-radius: 8px;
    padding: 12px;
    text-align: center;
    transition: border-color 0.15s, background-color 0.15s;
}
.dropzone.dragover {
    border-color: var(--bs-primary, #0d6efd);
    background-color: rgba(13, 110, 253, 0.08);
}
.dropzone .dropzone-hint {
    font-size: 0.85em;
    color: var(--bs-secondary-color, #6c757d);
    margin-bottom: 8px;
}
#md_preview {
    max-height: 70vh;
    overflow-y: auto;
}
"""

# Forward files dropped on the .dropzone onto the Shiny file input inside it,
# so drag-and-drop behaves exactly like picking files with the Browse button.
DROPZONE_JS = """
document.addEventListener('DOMContentLoaded', function() {
    const zone = document.querySelector('.dropzone');
    const input = zone && zone.querySelector('input[type=file]');
    if (!zone || !input) return;

    ['dragenter', 'dragover'].forEach(evt =>
        zone.addEventListener(evt, e => {
            e.preventDefault();
            zone.classList.add('dragover');
        })
    );
    ['dragleave', 'drop'].forEach(evt =>
        zone.addEventListener(evt, e => {
            e.preventDefault();
            zone.classList.remove('dragover');
        })
    );
    zone.addEventListener('drop', e => {
        const dt = new DataTransfer();
        for (const f of e.dataTransfer.files) {
            if (f.name.toLowerCase().endsWith('.pdf')) dt.items.add(f);
        }
        if (!dt.files.length) return;
        input.files = dt.files;
        input.dispatchEvent(new Event('change', { bubbles: true }));
    });
});
"""

app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.tags.style(DROPZONE_CSS),
        ui.tags.script(DROPZONE_JS),
        ui.div(
            ui.p("Drag & drop PDFs here", class_="dropzone-hint"),
            ui.input_file(
                "pdfs",
                None,
                accept=[".pdf"],
                multiple=True,
                button_label="Browse…",
                placeholder="No files selected",
            ),
            class_="dropzone",
        ),
        ui.input_text(
            "output_dir",
            "Local output folder",
            value=str(DEFAULT_OUTPUT_DIR),
        ),
        ui.accordion(
            ui.accordion_panel(
                "LiteParse options",
                ui.input_checkbox("ocr", "Enable OCR", value=True),
                ui.input_text("ocr_language", "OCR language", value="eng"),
                ui.input_numeric("max_pages", "Max pages", value=1000, min=1),
                ui.input_text(
                    "target_pages",
                    "Target pages (e.g. 1-5,8; blank = all)",
                    value="",
                ),
                ui.input_numeric("dpi", "DPI", value=150, min=50, max=600),
                ui.input_checkbox(
                    "preserve_small_text", "Preserve small text", value=False
                ),
                ui.input_password("password", "PDF password (if any)", value=""),
            ),
            open=False,
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
    ui.card(
        ui.card_header("Markdown preview"),
        ui.output_ui("preview_picker"),
        ui.output_ui("md_preview"),
    ),
    title="PDF → Markdown (LiteParse)",
)


def build_lit_args(pdf_path: Path, txt_output: Path, opts: dict) -> list[str]:
    args = [
        "lit", "parse", str(pdf_path),
        "--format", "text",
        "-o", str(txt_output),
        "--ocr-language", opts["ocr_language"] or "eng",
        "--max-pages", str(opts["max_pages"] or 1000),
        "--dpi", str(opts["dpi"] or 150),
    ]
    if not opts["ocr"]:
        args.append("--no-ocr")
    if opts["target_pages"].strip():
        args += ["--target-pages", opts["target_pages"].strip()]
    if opts["preserve_small_text"]:
        args.append("--preserve-small-text")
    if opts["password"]:
        args += ["--password", opts["password"]]
    return args


def convert_pdf(pdf_path: Path, output_dir: Path, opts: dict) -> Path:
    """Convert one PDF to Markdown with the LiteParse CLI. Returns the .md path."""
    txt_output = output_dir / f"{pdf_path.stem}.txt"
    subprocess.run(
        build_lit_args(pdf_path, txt_output, opts),
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

        opts = {
            "ocr": input.ocr(),
            "ocr_language": input.ocr_language(),
            "max_pages": input.max_pages(),
            "target_pages": input.target_pages(),
            "dpi": input.dpi(),
            "preserve_small_text": input.preserve_small_text(),
            "password": input.password(),
        }

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
                        md_path = convert_pdf(pdf_path, output_dir, opts)
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
                "Select or drag in one or more PDFs, choose where to save the "
                "Markdown files, then click “Convert to Markdown”.",
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

    @render.ui
    def preview_picker():
        files = converted_files()
        if not files:
            return ui.p("Converted files will be previewable here.", class_="text-muted")
        return ui.input_select(
            "preview_file",
            "File to preview",
            choices={str(p): p.name for p in files},
        )

    @render.ui
    def md_preview():
        if not converted_files():
            return None
        try:
            selected = input.preview_file()
        except Exception:
            return None
        if not selected:
            return None
        path = Path(selected)
        if not path.exists():
            return ui.p("File no longer exists on disk.", class_="text-danger")
        text = path.read_text(errors="replace")
        if len(text) > PREVIEW_CHAR_LIMIT:
            text = text[:PREVIEW_CHAR_LIMIT] + "\n\n*…preview truncated…*"
        return ui.markdown(text)

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
