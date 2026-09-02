#!/usr/bin/env python3
"""Turn a Markdown file into RTF, so it opens in Word and prints properly.

Written because there is no pandoc on this machine and the enquiry letter has
three tables in it that matter. Handles the subset this project actually uses:
headings, bold, italic, inline code, links, bullet and numbered lists, block
quotes, horizontal rules and pipe tables.

    ./tools/md2rtf.py letter.md            -> letter.rtf
    ./tools/md2rtf.py letter.md out.rtf

RTF is a 1987 format and shows it. Three things to know if this ever needs
changing: braces and backslashes must be escaped or the file will not open;
anything outside ASCII has to go out as a \\uNNNN escape with an ASCII fallback
character after it; and sizes are in half-points, so 24 means 12pt.
"""

import os
import re
import sys

PT = 2  # RTF measures type in half-points


def esc(text):
    """Escape a run of plain text for RTF."""
    out = []
    for ch in text:
        if ch in "\\{}":
            out.append("\\" + ch)
        elif ord(ch) < 128:
            out.append(ch)
        else:
            # \uN? — the trailing character is what readers that predate
            # Unicode fall back to.
            fallback = {
                0x2018: "'", 0x2019: "'", 0x201C: '"', 0x201D: '"',
                0x2013: "-", 0x2014: "-", 0x00A0: " ", 0x2265: ">=",
                0x00D7: "x", 0x00B7: "-", 0x2192: "->", 0x2190: "<-",
            }.get(ord(ch), "?")
            out.append("\\u%d%s" % (ord(ch), fallback))
    return "".join(out)


def inline(text):
    """Bold, italic, code and links inside a line."""
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    parts, pos = [], 0
    pattern = re.compile(r"(\*\*.+?\*\*|__.+?__|\*[^*]+?\*|`[^`]+?`)", re.S)
    for m in pattern.finditer(text):
        parts.append(esc(text[pos:m.start()]))
        tok = m.group(0)
        if tok.startswith(("**", "__")):
            parts.append(r"{\b " + esc(tok[2:-2]) + "}")
        elif tok.startswith("`"):
            parts.append(r"{\f1 " + esc(tok[1:-1]) + "}")
        else:
            parts.append(r"{\i " + esc(tok[1:-1]) + "}")
        pos = m.end()
    parts.append(esc(text[pos:]))
    return "".join(parts)


def table(rows):
    """A pipe table as a real RTF table, so it survives into Word."""
    cols = max(len(r) for r in rows)
    width = int(9000 / cols)
    out = []
    for i, row in enumerate(rows):
        cells = (row + [""] * cols)[:cols]
        out.append(r"\trowd\trgaph108\trleft0")
        for c in range(cols):
            out.append(r"\clbrdrt\brdrs\brdrw10\clbrdrl\brdrs\brdrw10"
                       r"\clbrdrb\brdrs\brdrw10\clbrdrr\brdrs\brdrw10"
                       r"\cellx%d" % (width * (c + 1)))
        for cell in cells:
            body = inline(cell)
            if i == 0:
                body = r"{\b " + body + "}"
            out.append(r"\intbl " + body + r"\cell")
        out.append(r"\row")
    return "\n".join(out) + "\n\\pard\n"


def paragraphs(md):
    """Join wrapped lines back into paragraphs.

    Markdown source is hard-wrapped at 80 columns. Emitting one \\par per source
    line reproduces those breaks in Word, which looks wrong at any other page
    width, and splits **bold** that straddles a line so the asterisks survive
    into the output. Headings, list items, table rows, rules and quotes each stay
    on their own line.
    """
    def standalone(ln):
        t = ln.strip()
        return (not t or t.startswith(("#", ">", "|"))
                or re.match(r"^\s*([-*]\s+|\d+\.\s+)", ln)
                or re.fullmatch(r"-{3,}|\*{3,}", t))

    out, buf = [], []
    for ln in md.split("\n"):
        if standalone(ln):
            if buf:
                out.append(" ".join(buf))
                buf = []
            out.append(ln)
        else:
            buf.append(ln.strip())
    if buf:
        out.append(" ".join(buf))
    return out


def convert(md):
    body, lines, i = [], paragraphs(md), 0
    while i < len(lines):
        line = lines[i].rstrip()

        # Pipe table: a header row, an alignment row, then data.
        if (line.startswith("|") and i + 1 < len(lines)
                and re.fullmatch(r"\|[\s:|-]+\|", lines[i + 1].strip())):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                raw = lines[i].strip().strip("|")
                if not re.fullmatch(r"[\s:|-]+", raw):
                    rows.append([c.strip() for c in raw.split("|")])
                i += 1
            body.append(table(rows))
            continue

        if not line.strip():
            body.append(r"\par")
        elif re.fullmatch(r"-{3,}|\*{3,}", line.strip()):
            body.append(r"\pard\brdrb\brdrs\brdrw10\brsp20 \par\pard\par")
        elif line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            size = {1: 17, 2: 14, 3: 12}.get(level, 11) * PT
            body.append(r"\pard\sb240\sa120\keepn\b\fs%d %s\b0\fs22\par"
                        % (size, inline(line.lstrip("#").strip())))
        elif line.startswith(">"):
            body.append(r"\pard\li567\i %s\i0\par\pard"
                        % inline(line.lstrip(">").strip()))
        elif re.match(r"^\s*[-*]\s+", line):
            body.append(r"\pard\li360\fi-180 \'95  %s\par\pard"
                        % inline(re.sub(r"^\s*[-*]\s+", "", line)))
        elif re.match(r"^\s*\d+\.\s+", line):
            m = re.match(r"^\s*(\d+)\.\s+(.*)", line)
            body.append(r"\pard\li360\fi-180 %s.  %s\par\pard"
                        % (m.group(1), inline(m.group(2))))
        else:
            body.append(r"\pard %s\par" % inline(line))
        i += 1

    return ("{\\rtf1\\ansi\\ansicpg1252\\deff0\n"
            "{\\fonttbl{\\f0\\froman Times New Roman;}"
            "{\\f1\\fmodern Courier New;}}\n"
            "\\f0\\fs22\n" + "\n".join(body) + "\n}\n")


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    src = sys.argv[1]
    dest = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(src)[0] + ".rtf"
    rtf = convert(open(src, encoding="utf-8").read())
    open(dest, "w", encoding="ascii", errors="backslashreplace").write(rtf)
    print("wrote %s (%.1f KB)" % (dest, os.path.getsize(dest) / 1024))


if __name__ == "__main__":
    main()
