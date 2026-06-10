# PDFtoMD

A small [Shiny for Python](https://shiny.posit.co/py/) app that batch-converts
PDF files to Markdown using the [LiteParse](https://pypi.org/project/liteparse/)
CLI — a desktop-friendly replacement for the original Google Colab workflow.

## Features

- Select one or more PDFs through the browser UI, or drag & drop them
  onto the upload area
- Batch conversion with a progress bar and per-file success/failure status
- Markdown preview pane for inspecting converted files in the browser
- LiteParse options: OCR on/off, OCR language, max pages, target pages
  (e.g. `1-5,8`), DPI, preserve small text, and PDF password
- Markdown files are written directly to a local folder of your choice
  (defaults to `~/markdown_output`)
- Optionally download all converted files as a single ZIP

## Setup

```bash
pip install -r requirements.txt
```

This installs Shiny and LiteParse (which provides the `lit` command-line tool
the app shells out to).

## Run

```bash
shiny run app.py
```

Then open http://127.0.0.1:8000 in your browser:

1. Click **Browse…** and select your PDF files.
2. (Optional) Change the local output folder.
3. Click **Convert to Markdown**.
4. Find the `.md` files in the output folder, or click **Download ZIP**.

> Note: the "local output folder" is local to the machine running the app.
> If you run the app on your own computer (the usual case), that's your
> computer. If you host it on a server, use the ZIP download instead.
