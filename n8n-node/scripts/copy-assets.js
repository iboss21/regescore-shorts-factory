// Copy non-TS assets (icons) from src to dist so n8n can render node icons.
const fs = require('fs');
const path = require('path');
const SRC = path.resolve('src');
const DIST = path.resolve('dist');
function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(full);
    else if (/\.(svg|png|json)$/i.test(entry.name)) {
      const dest = path.join(DIST, path.relative(SRC, full));
      fs.mkdirSync(path.dirname(dest), { recursive: true });
      fs.copyFileSync(full, dest);
    }
  }
}
walk(SRC);
