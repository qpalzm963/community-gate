"""由 docs/user-manual.md 產生 docs/user-manual.html（側邊目錄、深淺色、列印樣式）。

用法（在專案根目錄）：
    uvx --with markdown python docs/manual/build.py

修改說明書請改 user-manual.md，再執行本腳本；不要直接改 HTML。
"""
import re
from pathlib import Path

import markdown

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "user-manual.md"
OUT = HERE.parent / "user-manual.html"
TEMPLATE = HERE / "template.html"


def slugify(value: str, sep: str) -> str:
    # 與 GitHub 錨點規則一致（保留中文），md 內的目錄連結才能在 HTML 中使用
    v = re.sub(r"[^\w\- ]", "", value.strip().lower(), flags=re.U)
    return v.replace(" ", sep)


def toc_html(tokens) -> str:
    parts = []
    for t in tokens:
        if t["level"] == 1 and t["name"].startswith("社區出入"):
            parts.append(toc_html(t["children"]))
            continue
        cls = "lvl1" if t["level"] == 1 else "lvl2"
        parts.append(f'<a class="{cls}" href="#{t["id"]}">{t["name"]}</a>')
        if t["children"]:
            parts.append(toc_html(t["children"]))
    return "\n".join(parts)


def main() -> None:
    md = SRC.read_text(encoding="utf-8")
    # HTML 版改用側邊欄目錄，移除 Markdown 內的「目錄」段落
    md = re.sub(r"## 目錄\n.*?\n---\n", "", md, flags=re.S)
    m = markdown.Markdown(
        extensions=["tables", "fenced_code", "toc", "sane_lists"],
        extension_configs={"toc": {"slugify": slugify, "toc_depth": "1-2"}},
    )
    body = m.convert(md)
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("{{NAV}}", toc_html(m.toc_tokens)).replace("{{BODY}}", body)
    OUT.write_text(html, encoding="utf-8")
    print(f"已產生 {OUT.relative_to(Path.cwd()) if OUT.is_relative_to(Path.cwd()) else OUT}")


if __name__ == "__main__":
    main()
