// 简单的语法检查脚本
// 检查我们添加的缓存系统代码

const code = `
// 分页预加载缓存系统
const kbPageCache = new Map();
const CACHE_EXPIRY_MS = 5 * 60 * 1000;
const CACHE_MAX_SIZE = 10;

function getCacheKey(page, params) {
    return \`\${page}_\${params.toString()}\`;
}

function getFromCache(cacheKey) {
    const cached = kbPageCache.get(cacheKey);
    if (!cached) return null;
    
    if (Date.now() - cached.timestamp > CACHE_EXPIRY_MS) {
        kbPageCache.delete(cacheKey);
        return null;
    }
    
    return cached.data;
}

function saveToCache(cacheKey, data) {
    if (kbPageCache.size >= CACHE_MAX_SIZE) {
        const firstKey = kbPageCache.keys().next().value;
        kbPageCache.delete(firstKey);
    }
    
    kbPageCache.set(cacheKey, {
        data: data,
        timestamp: Date.now()
    });
}

function clearKBCache() {
    kbPageCache.clear();
}

async function prefetchKBNextPage(currentPage, params) {
    try {
        const nextPage = currentPage + 1;
        const totalPages = Math.ceil(kbTotal / kbPageSize);
        
        if (nextPage > totalPages) return;
        
        const nextParams = new URLSearchParams(params.toString());
        nextParams.set('page', nextPage);
        
        const cacheKey = getCacheKey(nextPage, nextParams);
        
        if (getFromCache(cacheKey)) return;
        
        const res = await fetch(\`\${API_BASE}/kb/data?\${nextParams.toString()}\`, {
            method: 'GET',
            credentials: 'same-origin'
        });
        
        if (!res.ok) return;
        
        const data = await res.json();
        
        saveToCache(cacheKey, data);
        
        console.log(\`✓ 预加载第 \${nextPage} 页成功\`);
    } catch (e) {
        console.debug('预加载失败（不影响功能）:', e.message);
    }
}
`;

try {
    new Function(code);
    console.log('✅ 语法检查通过！');
    console.log('所有添加的代码语法正确。');
} catch (e) {
    console.error('❌ 语法错误：', e.message);
    process.exit(1);
}
