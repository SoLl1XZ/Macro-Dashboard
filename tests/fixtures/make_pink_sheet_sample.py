"""Write pink_sheet_sample.xlsx: a tiny workbook shaped like the World Bank's Pink Sheet.

Run it again only if the test needs a different sample: python3 tests/fixtures/make_pink_sheet_sample.py
Like the real file it has a sheet before "Monthly Prices", title lines, a header row, a
units row, months as "2026M07", shared strings, one inline string and "…" for no price.
"""

import zipfile
from pathlib import Path

MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"

SHARED = ["World Bank Commodity Price Data (The Pink Sheet)", "Crude oil, Brent", "Gold",
          "($/bbl)", "($/troy oz)", "2026M07", "2026M08", "2026M09", "…"]


def shared(text: str) -> str:
    return str(SHARED.index(text))


def cell(ref: str, text: str, kind: str = "number") -> str:
    if kind == "shared":
        return f'<c r="{ref}" t="s"><v>{shared(text)}</v></c>'
    if kind == "inline":
        return f'<c r="{ref}" t="inlineStr"><is><t>{text}</t></is></c>'
    return f'<c r="{ref}"><v>{text}</v></c>'


ROWS = [
    (1, [cell("A1", "World Bank Commodity Price Data (The Pink Sheet)", "shared")]),
    (5, [cell("B5", "Crude oil, Brent", "shared"), cell("C5", "Gold", "shared"),
         cell("D5", "Silver", "inline")]),
    (6, [cell("B6", "($/bbl)", "shared"), cell("C6", "($/troy oz)", "shared"),
         cell("D6", "($/troy oz)", "shared")]),
    (7, [cell("A7", "2026M07", "shared"), cell("B7", "83.7"), cell("C7", "4073"), cell("D7", "58.8")]),
    (8, [cell("A8", "2026M08", "shared"), cell("B8", "90.9"), cell("C8", "…", "shared"), cell("D8", "65.4")]),
    (9, [cell("A9", "2026M09", "shared"), cell("B9", "116.8"), cell("C9", "4319"), cell("D9", "64.6")]),
]


def main() -> None:
    sheet_data = "".join(f'<row r="{number}">{"".join(cells)}</row>' for number, cells in ROWS)
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '</Types>'),
        "xl/workbook.xml": (
            f'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="{MAIN}" xmlns:r="{REL}"><sheets>'
            '<sheet name="Description" sheetId="1" r:id="rId1"/>'
            '<sheet name="Monthly Prices" sheetId="2" r:id="rId2"/>'
            '</sheets></workbook>'),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="worksheet" Target="worksheets/sheet2.xml"/>'
            '</Relationships>'),
        "xl/sharedStrings.xml": (
            f'<?xml version="1.0" encoding="UTF-8"?><sst xmlns="{MAIN}">'
            + "".join(f"<si><t>{text}</t></si>" for text in SHARED) + "</sst>"),
        "xl/worksheets/sheet1.xml": f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{MAIN}"><sheetData/></worksheet>',
        "xl/worksheets/sheet2.xml": (
            f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="{MAIN}">'
            f"<sheetData>{sheet_data}</sheetData></worksheet>"),
    }
    path = Path(__file__).with_name("pink_sheet_sample.xlsx")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as book:
        for name, content in files.items():
            book.writestr(zipfile.ZipInfo(name, date_time=(2026, 10, 8, 0, 0, 0)), content.encode("utf-8"))
    print(f"Wrote {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
