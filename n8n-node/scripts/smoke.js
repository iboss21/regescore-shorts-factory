
const pkg = require('../dist/index.js');
if (!pkg || !Array.isArray(pkg.nodes)) {
  console.error('Smoke: invalid export surface');
  process.exit(1);
}
console.log('Smoke: nodes exported:', pkg.nodes.length);
