"""A very small xlsx reader.

The Environment Agency publishes the EDM returns as xlsx, and openpyxl is not
installed on this machine. These files are simple: one sheet, no formulas we
care about, no merged cells in the data rows. That is little enough to read
with the standard library, and it keeps the tooling dependency-free.

Yields one dict per row, keyed by column letter, e.g. {'A': 'SVT01315', ...}.
Empty cells are absent rather than None, so use .get().
"""

import re
import zipfile
from xml.etree import ElementTree as ET

NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"


def sheets(path):
    """Return [(name, 'xl/worksheets/sheetN.xml')] in workbook order."""
    z = zipfile.ZipFile(path)
    rels = {}
    rel_xml = ET.fromstring(z.read("xl/_rels/workbook.xml.rels"))
    for r in rel_xml:
        rels[r.get("Id")] = r.get("Target").lstrip("/")
    out = []
    rid = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
    for s in ET.fromstring(z.read("xl/workbook.xml")).iter(NS + "sheet"):
        target = rels.get(s.get(rid), "")
        if not target.startswith("xl/"):
            target = "xl/" + target
        out.append((s.get("name"), target))
    return out


def rows(path, sheet="xl/worksheets/sheet1.xml"):
    z = zipfile.ZipFile(path)

    # Shared strings are a single table the cells index into; a cell with
    # t="s" holds an offset, not the text itself.
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")):
            shared.append("".join(t.text or "" for t in si.iter(NS + "t")))

    # iterparse and clear as we go: the all-companies return is 20k+ rows and
    # building the whole tree first is needlessly slow.
    for _, el in ET.iterparse(z.open(sheet), events=("end",)):
        if el.tag != NS + "row":
            continue
        out = {}
        for c in el.findall(NS + "c"):
            v = c.find(NS + "v")
            if v is None or v.text is None:
                continue
            if c.get("t") == "s":
                val = shared[int(v.text)]
            else:
                val = v.text
            col = re.match(r"[A-Z]+", c.get("r") or "A").group()
            out[col] = val
        yield out
        el.clear()
