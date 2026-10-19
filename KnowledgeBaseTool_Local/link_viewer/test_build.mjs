import test from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync, writeFileSync, readFileSync, mkdirSync, copyFileSync, symlinkSync, readdirSync, existsSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import postcss from 'postcss';

const root = dirname(fileURLToPath(import.meta.url));

function fixture(t) {
  const dir = mkdtempSync(join(tmpdir(), 'kmatrix-build-'));
  t.after(() => rmSync(dir, { recursive: true, force: true }));
  copyFileSync(join(root, 'build.js'), join(dir, 'build.js'));
  writeFileSync(join(dir, 'package.json'), '{"type":"module"}');
  symlinkSync(join(root, 'node_modules'), join(dir, 'node_modules'), 'dir');
  const files = {
    'app_v8.js': 'function demo() { return 1 + 2; } console.log(demo());',
    'styles.css': '.probe { content: "two  spaces: ; }"; background: url("data:image/svg+xml,<svg data-label=\'two  spaces\'></svg>"); }',
    'extra_styles.css': '.extra { width: calc(100% - 2px); }',
    'index.html': '<link href="styles.css?v=1"><link href="extra_styles.css?v=2"><link href="scroll-performance.css?v=4"><link href="vendor/style.css"><script src="login_bootstrap.js?v=1"></script><script src="app_v8.js?v=3"></script>',
    'platform_intro.html': '<link href="/platform_intro.css">',
    'test_optimization.html': '<p>diagnostic</p>',
    'design-system.css': ':root { --radius: 2px; }',
    'loading-states.css': '.loading { opacity: .5; }',
    'scroll-performance.css': '.scroll { overflow: auto; }',
    'platform_intro.css': '.intro { color: black; }',
    'loading-manager.js': 'window.loading = true;',
    'login_bootstrap.js': 'window.login = true;',
    'app_v8.min.js': 'historical JS',
    'styles.min.css': 'historical CSS',
    'extra_styles.min.css': 'historical extra CSS',
    'index.prod.html': 'historical HTML',
  };
  for (const [name, content] of Object.entries(files)) writeFileSync(join(dir, name), content);
  mkdirSync(join(dir, 'vendor'));
  writeFileSync(join(dir, 'vendor/style.css'), 'body { color: black; }');
  mkdirSync(join(dir, 'dist'));
  writeFileSync(join(dir, 'dist/stale.js'), 'old build');
  return { dir, files };
}

function run(dir, args = []) {
  return spawnSync(process.execPath, [join(dir, 'build.js'), ...args], { cwd: dir, encoding: 'utf8' });
}

function artifactContents(dir) {
  return Object.fromEntries(readdirSync(join(dir, 'dist'))
    .filter(name => name !== 'build-report.json' && name !== 'vendor')
    .map(name => [name, readFileSync(join(dir, 'dist', name), 'utf8')]));
}

test('default builds preserve source, include runtime assets and produce stable output', t => {
  const { dir, files } = fixture(t);
  const first = run(dir);
  assert.equal(first.status, 0, first.stderr);
  for (const [name, content] of Object.entries(files)) {
    assert.equal(readFileSync(join(dir, name), 'utf8'), content, `source changed: ${name}`);
  }
  assert.equal(existsSync(join(dir, 'dist/stale.js')), false);
  for (const name of ['scroll-performance.css', 'platform_intro.html', 'platform_intro.css', 'login_bootstrap.js']) {
    assert.equal(existsSync(join(dir, 'dist', name)), true);
  }
  const html = readFileSync(join(dir, 'dist/index.html'), 'utf8');
  assert.match(html, /app_v8\.min\.js\?v=[a-f0-9]{12}/);
  assert.match(html, /extra_styles\.min\.css\?v=[a-f0-9]{12}/);
  const declarations = {};
  postcss.parse(readFileSync(join(dir, 'dist/styles.min.css'), 'utf8'))
    .walkDecls(decl => { declarations[decl.prop] = decl.value; });
  assert.equal(declarations.content.slice(1, -1), 'two  spaces: ; }');
  assert.ok(declarations.background.includes('two  spaces'));
  const before = artifactContents(dir);
  const second = run(dir);
  assert.equal(second.status, 0, second.stderr);
  assert.deepEqual(artifactContents(dir), before);
  writeFileSync(join(dir, 'app_v8.js'), files['app_v8.js'] + '\nconsole.log("changed");');
  const changed = run(dir);
  assert.equal(changed.status, 0, changed.stderr);
  assert.notEqual(readFileSync(join(dir, 'dist/index.html'), 'utf8'), html);
});

test('missing runtime asset fails without replacing the previous build', t => {
  const { dir } = fixture(t);
  rmSync(join(dir, 'scroll-performance.css'));
  const result = run(dir);
  assert.notEqual(result.status, 0);
  assert.equal(readFileSync(join(dir, 'dist/stale.js'), 'utf8'), 'old build');
  assert.deepEqual(readdirSync(dir).filter(name => name.startsWith('.build-')), []);
});

test('invalid CSS fails without replacing the previous build', t => {
  const { dir } = fixture(t);
  writeFileSync(join(dir, 'styles.css'), '.broken { color: red;');
  const result = run(dir);
  assert.notEqual(result.status, 0);
  assert.equal(readFileSync(join(dir, 'dist/stale.js'), 'utf8'), 'old build');
});

test('legacy output requires an explicit flag', t => {
  const { dir } = fixture(t);
  const result = run(dir, ['--legacy']);
  assert.equal(result.status, 0, result.stderr);
  assert.equal(readFileSync(join(dir, 'index.prod.html'), 'utf8'), readFileSync(join(dir, 'dist/index.html'), 'utf8'));
  assert.equal(readFileSync(join(dir, 'app_v8.min.js'), 'utf8'), readFileSync(join(dir, 'dist/app_v8.min.js'), 'utf8'));
});
