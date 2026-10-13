#!/usr/bin/env python3
"""scope_css.py — scope every rule in a scene's <style> blocks to its own composition root.

usage: scope_css.py [--check] <composition.html> [...]

Assembled scenes share one page, so an unprefixed class rule (.glyph, .badge, .stmt ...) from one scene can
override another's. Each selector becomes `[data-composition-id="<sid>"] <selector>`, where <sid> is the first
data-composition-id in the file. Selectors that already start with that scope are left alone, `#root` becomes the
scoped root itself, rules inside @media / @supports / @container / @layer are scoped too, and @font-face,
@keyframes and other @-rules are copied verbatim. Comments are kept. Idempotent: a second run changes nothing.

--check  rewrite nothing; list every unscoped selector and exit 1 if there is any.

Also importable: scope_file(path, check=False) -> (sid, changed, unscoped).
"""
import re
import sys

NESTED_AT = ('@media', '@supports', '@container', '@layer', '@document', '@scope')
STYLE_RE = re.compile(r'(<style\b[^>]*>)(.*?)(</style>)', re.S | re.I)
COMMENT_RE = re.compile(r'/\*.*?\*/', re.S)


def _skip(css, k):
    """If css[k] opens a comment or a string, return the index just past it; else None."""
    if css.startswith('/*', k):
        e = css.find('*/', k + 2)
        return len(css) if e < 0 else e + 2
    if css[k] in '"\'':
        q, e = css[k], k + 1
        while e < len(css) and css[e] != q:
            e += 2 if css[e] == '\\' else 1
        return e + 1
    return None


def _find_open(css, i):
    """Index of the next '{' at or after i that is not inside a comment or string, or -1."""
    k = i
    while k < len(css):
        s = _skip(css, k)
        if s is not None:
            k = s
            continue
        if css[k] == '{':
            return k
        k += 1
    return -1


def _match_close(css, j):
    """Index of the '}' matching the '{' at j (comments and strings skipped)."""
    depth, k = 0, j
    while k < len(css):
        s = _skip(css, k)
        if s is not None:
            k = s
            continue
        if css[k] == '{':
            depth += 1
        elif css[k] == '}':
            depth -= 1
            if depth == 0:
                return k
        k += 1
    return len(css) - 1


def _scope_selector(s, scope):
    if s.startswith(scope):
        return s
    if s == '#root':
        return f'{scope}#root'
    if s.startswith('#root') and not re.match(r'#root[\w-]', s):
        return scope + s[len('#root'):]
    return f'{scope} {s}'


def scope_block(css, sid, unscoped=None):
    """Return css with every rule scoped to sid. If unscoped is a list, append unscoped selectors to it."""
    scope = f'[data-composition-id="{sid}"]'
    out, i = [], 0
    while i < len(css):
        j = _find_open(css, i)
        if j < 0:
            out.append(css[i:])
            break
        head = css[i:j]
        k = _match_close(css, j)
        body = css[j:k + 1]
        # statement at-rules (@import ...;) that precede this rule are copied verbatim
        clean = COMMENT_RE.sub(' ', head)
        if ';' in clean:
            cut = head.rfind(';') + 1
            out.append(head[:cut])
            head = head[cut:]
            clean = COMMENT_RE.sub(' ', head)
        comments = ''.join(COMMENT_RE.findall(head))
        sel = re.sub(r'\s+', ' ', clean).strip()
        lead = head[:len(head) - len(head.lstrip())] + (comments + '\n        ' if comments else '')
        if not sel:
            out.append(head + body)
        elif sel.startswith('@'):
            if sel.lower().startswith(NESTED_AT):
                out.append(head + '{' + scope_block(body[1:-1], sid, unscoped) + '}')
            else:
                out.append(head + body)
        else:
            parts = [p.strip() for p in sel.split(',')]
            if unscoped is not None:
                unscoped.extend(p for p in parts if not p.startswith(scope))
            out.append(lead + ', '.join(_scope_selector(p, scope) for p in parts) + ' ' + body)
        i = k + 1
    return ''.join(out)


def scope_file(path, check=False):
    """Scope one composition file in place (or only report, with check=True).
    Returns (sid or None, changed: bool, unscoped: list[str] found before scoping)."""
    with open(path, encoding='utf-8') as fh:
        src = fh.read()
    m = re.search(r'data-composition-id="([^"]+)"', src)
    if not m:
        return None, False, []
    sid, unscoped = m.group(1), []
    new = STYLE_RE.sub(lambda mm: mm.group(1) + scope_block(mm.group(2), sid, unscoped) + mm.group(3), src)
    changed = new != src
    if changed and not check:
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(new)
    return sid, changed, unscoped


def main(argv):
    check = '--check' in argv
    paths = [a for a in argv if a != '--check']
    if not paths:
        print(__doc__.strip(), file=sys.stderr)
        return 2
    bad = 0
    for path in paths:
        sid, changed, unscoped = scope_file(path, check=check)
        if sid is None:
            print(f'{path}: no data-composition-id, skipped', file=sys.stderr)
            continue
        if check:
            for s in unscoped:
                print(f'{path}: unscoped selector: {s}')
            bad += len(unscoped)
            if not unscoped:
                print(f'{path}: ok ({sid})')
        else:
            print(f'{path}: scoped to {sid}' + ('' if changed else ' (unchanged)'))
    if check and bad:
        print(f'{bad} unscoped selector(s); run scope_css.py without --check to fix', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
