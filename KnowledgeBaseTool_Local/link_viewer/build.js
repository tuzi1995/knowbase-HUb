#!/usr/bin/env node

import { readFileSync, writeFileSync, mkdirSync, copyFileSync, existsSync, readdirSync, statSync } from 'fs';
import { join, dirname, basename } from 'path';
import { minify } from 'terser';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

const DIST_DIR = join(__dirname, 'dist');
const SRC_DIR = __dirname;

// 创建dist目录
if (!existsSync(DIST_DIR)) {
  mkdirSync(DIST_DIR, { recursive: true });
}

console.log('🚀 开始构建...\n');

// 1. 压缩 JavaScript
console.log('📦 压缩 JavaScript...');
const jsFiles = ['app_v8.js'];

for (const file of jsFiles) {
  const srcPath = join(SRC_DIR, file);
  const content = readFileSync(srcPath, 'utf8');
  
  console.log(`  处理: ${file} (${(content.length / 1024).toFixed(1)} KB)`);
  
  const result = await minify(content, {
    compress: {
      drop_console: false,
      drop_debugger: true,
      passes: 2,
      pure_funcs: ['console.debug']
    },
    mangle: {
      toplevel: false,
      keep_fnames: false
    },
    format: {
      comments: false
    }
  });
  
  const minFile = file.replace('.js', '.min.js');
  const distPath = join(DIST_DIR, minFile);
  writeFileSync(distPath, result.code);
  writeFileSync(join(SRC_DIR, minFile), result.code);
  
  const reduction = ((1 - result.code.length / content.length) * 100).toFixed(1);
  console.log(`  ✅ ${minFile} (${(result.code.length / 1024).toFixed(1)} KB, 减少 ${reduction}%)\n`);
}

// 2. 压缩 CSS
console.log('🎨 压缩 CSS...');
const cssFiles = ['styles.css', 'extra_styles.css'];

for (const file of cssFiles) {
  const srcPath = join(SRC_DIR, file);
  const content = readFileSync(srcPath, 'utf8');
  
  console.log(`  处理: ${file} (${(content.length / 1024).toFixed(1)} KB)`);
  
  // 简单的CSS压缩：移除注释、多余空格和换行
  let minified = content
    .replace(/\/\*[\s\S]*?\*\//g, '') // 移除注释
    .replace(/\s+/g, ' ') // 多个空格替换为单个
    .replace(/\s*([{}:;,])\s*/g, '$1') // 移除符号周围空格
    .replace(/;}/g, '}') // 移除最后的分号
    .trim();
  
  const minFile = file.replace('.css', '.min.css');
  const distPath = join(DIST_DIR, minFile);
  writeFileSync(distPath, minified);
  writeFileSync(join(SRC_DIR, minFile), minified);
  
  const reduction = ((1 - minified.length / content.length) * 100).toFixed(1);
  console.log(`  ✅ ${minFile} (${(minified.length / 1024).toFixed(1)} KB, 减少 ${reduction}%)\n`);
}

// 3. 复制HTML文件并更新引用
console.log('📄 处理 HTML 文件...');
const htmlFiles = ['index.html', 'test_optimization.html'];

for (const file of htmlFiles) {
  const srcPath = join(SRC_DIR, file);
  let content = readFileSync(srcPath, 'utf8');
  
  // 更新JS引用
  content = content.replace(/app_v8\.js(\?v=\d+)?/g, 'app_v8.min.js');
  
  // 更新CSS引用
  content = content.replace(/styles\.css(\?v=\d+)?/g, 'styles.min.css');
  content = content.replace(/extra_styles\.css(\?v=\d+)?/g, 'extra_styles.min.css');
  
  const distPath = join(DIST_DIR, file);
  writeFileSync(distPath, content);

  if (file === 'index.html') {
    writeFileSync(join(SRC_DIR, 'index.prod.html'), content);
  }
  
  console.log(`  ✅ ${file}`);
}

// 4. 复制vendor目录
console.log('\n📚 复制 vendor 目录...');
const vendorSrc = join(SRC_DIR, 'vendor');
const vendorDist = join(DIST_DIR, 'vendor');

function copyDir(src, dest) {
  if (!existsSync(dest)) {
    mkdirSync(dest, { recursive: true });
  }
  
  const entries = readdirSync(src);
  
  for (const entry of entries) {
    const srcPath = join(src, entry);
    const destPath = join(dest, entry);
    
    if (statSync(srcPath).isDirectory()) {
      copyDir(srcPath, destPath);
    } else {
      copyFileSync(srcPath, destPath);
    }
  }
}

copyDir(vendorSrc, vendorDist);
console.log('  ✅ vendor 目录已复制');

// 5. 生成构建报告
console.log('\n📊 生成构建报告...');

const report = {
  buildTime: new Date().toISOString(),
  files: {
    js: jsFiles.map(f => {
      const original = statSync(join(SRC_DIR, f)).size;
      const minified = statSync(join(DIST_DIR, f.replace('.js', '.min.js'))).size;
      return {
        name: f,
        original: `${(original / 1024).toFixed(1)} KB`,
        minified: `${(minified / 1024).toFixed(1)} KB`,
        reduction: `${((1 - minified / original) * 100).toFixed(1)}%`
      };
    }),
    css: cssFiles.map(f => {
      const original = statSync(join(SRC_DIR, f)).size;
      const minified = statSync(join(DIST_DIR, f.replace('.css', '.min.css'))).size;
      return {
        name: f,
        original: `${(original / 1024).toFixed(1)} KB`,
        minified: `${(minified / 1024).toFixed(1)} KB`,
        reduction: `${((1 - minified / original) * 100).toFixed(1)}%`
      };
    })
  }
};

writeFileSync(join(DIST_DIR, 'build-report.json'), JSON.stringify(report, null, 2));

console.log('\n✅ 构建完成！');
console.log(`📁 输出目录: ${DIST_DIR}`);
console.log('\n📊 压缩统计:');
console.log('JavaScript:');
report.files.js.forEach(f => {
  console.log(`  ${f.name}: ${f.original} → ${f.minified} (减少 ${f.reduction})`);
});
console.log('CSS:');
report.files.css.forEach(f => {
  console.log(`  ${f.name}: ${f.original} → ${f.minified} (减少 ${f.reduction})`);
});
