"""Refresh local asset URLs after editing JavaScript, CSS or the bundled codec."""
import hashlib
import re
from pathlib import Path

root = Path(__file__).resolve().parents[1]
page = root / 'index.html'
html = page.read_text()
for name in ['app.js', 'styles.css', 'vendor/fflate-0.8.2.min.js']:
    digest = hashlib.sha256((root / name).read_bytes()).hexdigest()[:12]
    pattern = r'((?:src|href)=")' + re.escape(name) + r'(?:\?v=[^\"]*)?"'
    html, count = re.subn(pattern, lambda m: m[1] + name + '?v=' + digest + '"', html)
    if count != 1:
        raise SystemExit(f'Expected exactly one asset reference: {name}')
page.write_text(html)
