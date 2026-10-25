"""Pieces shared by the root-page tiles (build_index.py) and the detail-page header card (build_html.py)."""
import html


def split_name(text):
    """(html, length): one span per letter so a theme can bend the title (--i = index, --n = length on the heading);
    letters stay together per word, so a long title can only wrap between words."""
    words, idx = [], 0
    for w in text.split(" "):
        chars = "".join(f'<span class="ch" style="--i:{idx + k}" aria-hidden="true">{html.escape(ch)}</span>' for k, ch in enumerate(w))
        words.append(f'<span class="w">{chars}</span>')
        idx += len(w) + 1
    return " ".join(words), len(text)


# neutral card rules: a theme's tile.css restyles them through `.tile--<theme>`
TILE_BASE_CSS = """
.tile-frame { position: absolute; inset: 0; background: var(--tile); border: 2px solid var(--ink); border-radius: 14px;
              box-shadow: 0 10px 24px -14px rgba(0,0,0,.35); }
.tile-deco { position: absolute; inset: 0; pointer-events: none; }
.tile-text { position: relative; z-index: 3; }
.tile-name { margin: 0; font-size: 1.7rem; line-height: 1.1; }
.tile-name a { text-decoration: none; }
.tile-name .w { white-space: nowrap; }
.tile-name .ch { display: inline-block; }
.tile-tag { margin: 6px 0 0; color: var(--muted); }
.tile-meta { margin: 4px 0 0; font-size: .85rem; color: var(--muted); }
"""


def head_card_html(theme, name, tagline, meta_html, deco_html, filters_html):
    """the detail page's header: the theme's tile look (title, ribbon, decoration) as a wide card, filters inside"""
    name_html, name_len = split_name(name)
    filters = f'<div class="head-filters">{filters_html}</div>' if filters_html else ""
    return (f'<header class="page-head tile tile--{html.escape(theme)} head-card">'
            f'<div class="tile-frame"></div><div class="tile-deco">{deco_html}</div>'
            f'<div class="tile-text"><h1 class="tile-name" style="--n:{name_len}">{name_html}</h1>'
            f'<p class="tile-tag">{html.escape(tagline)}</p><p class="tile-meta">{meta_html}</p></div>'
            f'{filters}</header>')
