from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: python -m backend.app.services.doc_text_worker <file.doc>", file=sys.stderr)
        return 2
    path = Path(sys.argv[1])
    try:
        print(_extract_doc_text_with_word(path), end="")
        return 0
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1


def _extract_doc_text_with_word(path: Path) -> str:
    import pythoncom
    import win32com.client

    pythoncom.CoInitialize()
    word = None
    doc = None
    try:
        word = win32com.client.DispatchEx("Word.Application")
        word.Visible = False
        word.DisplayAlerts = 0
        doc = word.Documents.Open(str(path.resolve()), ReadOnly=True, AddToRecentFiles=False)
        return str(doc.Content.Text)
    finally:
        if doc is not None:
            doc.Close(False)
        if word is not None:
            word.Quit()
        pythoncom.CoUninitialize()


if __name__ == "__main__":
    raise SystemExit(main())
