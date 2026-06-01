/**
 * ==========================================
 * 加载状态集成补丁
 * ==========================================
 * 
 * 本文件包含需要在 app_v8.js 中添加的代码片段
 * 
 * 使用方法：
 * 1. 找到对应的函数位置
 * 2. 按照注释说明修改代码
 * 3. 测试功能是否正常
 * 
 * 优化：2026-04-22
 */

// ==========================================
// 补丁 1: KB 数据加载 - 添加骨架屏
// ==========================================
// 位置：第 7149 行附近
// 函数：加载 KB 数据的地方

/* 
原始代码：
```javascript
const tbody = document.getElementById('kbTableBody');
if (!tbody) return;
tbody.innerHTML = '<tr><td colspan="100" class="empty-message">加载中...</td></tr>';

try {
    const res = await api(`/kb/data?${params.toString()}`);
    // ...
}
```

修改为：
```javascript
const tbody = document.getElementById('kbTableBody');
if (!tbody) return;

// 显示骨架屏
LoadingManager.showSkeleton('kbTableBody', 'table', 5);

try {
    const res = await api(`/kb/data?${params.toString()}`);
    
    if (res.error) {
        LoadingManager.showEmptyState('kbTableBody', {
            icon: '⚠️',
            title: '加载失败',
            description: res.error
        });
        return;
    }
    
    // ... 原有的数据处理代码
    
    // 如果数据为空
    if (!data || data.length === 0) {
        LoadingManager.showEmptyState('kbTableBody', {
            icon: '📭',
            title: '暂无数据',
            description: '当前没有符合条件的知识库条目'
        });
        return;
    }
    
    // ... 继续原有代码
}
```
*/

// ==========================================
// 补丁 2: Links 数据加载 - 添加顶部进度条
// ==========================================
// 位置：第 3872 行附近
// 函数：async function loadLinks()

/*
原始代码：
```javascript
async function loadLinks() {
  try {
    const [res] = await Promise.all([
      // ...
    ]);
    // ...
  } catch (e) {
    console.error('Failed to load links:', e);
  }
}
```

修改为：
```javascript
async function loadLinks() {
  LoadingManager.showTopProgress();
  
  try {
    const [res] = await Promise.all([
      // ...
    ]);
    // ...
  } catch (e) {
    console.error('Failed to load links:', e);
    showToast('加载链接失败', 'error');
  } finally {
    LoadingManager.hideTopProgress();
  }
}
```
*/

// ==========================================
// 补丁 3: 保存按钮 - 添加按钮加载状态
// ==========================================
// 位置：搜索 "await api('/kb/update'" 找到保存函数

/*
示例代码：
```javascript
async function saveKBItem() {
  const saveBtn = document.getElementById('kbSaveBtn');
  
  // 设置按钮为加载状态
  LoadingManager.setButtonLoading(saveBtn, true);
  
  try {
    const res = await api('/kb/update', 'POST', data);
    
    if (res.success) {
      showToast('保存成功', 'success');
    } else {
      showToast('保存失败: ' + (res.message || '未知错误'), 'error');
    }
  } catch (e) {
    showToast('保存异常: ' + e.message, 'error');
  } finally {
    LoadingManager.setButtonLoading(saveBtn, false);
  }
}
```
*/

// ==========================================
// 补丁 4: 删除操作 - 添加按钮加载状态
// ==========================================
// 位置：第 7933 行附近
// 函数：删除 KB 数据

/*
原始代码：
```javascript
try {
    const res = await api('/kb/delete', 'POST', { ids: Array.from(selectedKBRows) });
    if (res.success) {
        alert('删除操作成功');
        // ...
    }
}
```

修改为：
```javascript
const deleteBtn = document.getElementById('kbDeleteBtn'); // 假设有这个按钮
LoadingManager.setButtonLoading(deleteBtn, true);

try {
    const res = await api('/kb/delete', 'POST', { ids: Array.from(selectedKBRows) });
    if (res.success) {
        showToast('删除成功', 'success');
        // ...
    }
} catch (e) {
    showToast('删除失败: ' + e.message, 'error');
} finally {
    LoadingManager.setButtonLoading(deleteBtn, false);
}
```
*/

// ==========================================
// 补丁 5: 同步操作 - 添加全屏加载
// ==========================================
// 位置：第 7748 行附近
// 函数：同步 KB 数据

/*
原始代码：
```javascript
try {
    const data = await api('/kb/sync', 'POST');
    if (data.success) {
        if (status) status.textContent = '✅ 同步完成';
    }
}
```

修改为：
```javascript
LoadingManager.showFullscreenLoading('正在同步数据，请稍候...');

try {
    const data = await api('/kb/sync', 'POST');
    if (data.success) {
        showToast('同步完成', 'success');
    }
} catch (e) {
    showToast('同步失败: ' + e.message, 'error');
} finally {
    LoadingManager.hideFullscreenLoading();
}
```
*/

// ==========================================
// 补丁 6: Matrix 数据加载 - 添加表格加载遮罩
// ==========================================
// 位置：第 10515 行附近
// 函数：加载 Matrix 数据

/*
原始代码：
```javascript
const res = await api(`/matrix/data?${params.toString()}`);
if (res.error) {
    tbody.innerHTML = `<tr><td colspan="100" class="error-message">加载失败: ${res.error}</td></tr>`;
    return;
}
```

修改为：
```javascript
LoadingManager.showTableLoading('matrixTableBody', '加载矩阵数据...');

try {
    const res = await api(`/matrix/data?${params.toString()}`);
    
    if (res.error) {
        LoadingManager.showEmptyState('matrixTableBody', {
            icon: '⚠️',
            title: '加载失败',
            description: res.error
        });
        return;
    }
    
    // ... 处理数据
    
} finally {
    LoadingManager.hideTableLoading('matrixTableBody');
}
```
*/

// ==========================================
// 补丁 7: 搜索功能 - 添加内联加载
// ==========================================
// 位置：搜索相关函数

/*
示例代码：
```javascript
async function searchKB(query) {
  const resultsContainer = document.getElementById('kbSearchResults');
  
  LoadingManager.showInlineLoading('kbSearchResults', '搜索中...');
  
  try {
    const res = await api(`/kb/search?q=${encodeURIComponent(query)}`);
    
    if (res.data && res.data.length > 0) {
      renderSearchResults(res.data);
    } else {
      LoadingManager.showEmptyState('kbSearchResults', {
        icon: '🔍',
        title: '未找到结果',
        description: `没有找到与 "${query}" 相关的内容`
      });
    }
  } catch (e) {
    LoadingManager.showEmptyState('kbSearchResults', {
      icon: '❌',
      title: '搜索失败',
      description: e.message
    });
  }
}
```
*/

// ==========================================
// 补丁 8: 批量操作 - 添加进度提示
// ==========================================
// 位置：批量提交相关函数

/*
示例代码：
```javascript
async function batchSubmit(items) {
  const total = items.length;
  let completed = 0;
  
  LoadingManager.showFullscreenLoading(`处理中 (0/${total})...`);
  
  try {
    for (const item of items) {
      await api('/kb/update', 'POST', item);
      completed++;
      
      // 更新进度
      const overlay = document.getElementById('fullscreen-loading-overlay');
      if (overlay) {
        const text = overlay.querySelector('.loading-text');
        if (text) {
          text.textContent = `处理中 (${completed}/${total})...`;
        }
      }
    }
    
    showToast(`批量操作完成，共处理 ${total} 条`, 'success');
    
  } catch (e) {
    showToast(`批量操作失败: ${e.message}`, 'error');
  } finally {
    LoadingManager.hideFullscreenLoading();
  }
}
```
*/

// ==========================================
// 补丁 9: 导出功能 - 添加进度提示
// ==========================================

/*
示例代码：
```javascript
async function exportData() {
  const exportBtn = document.getElementById('exportBtn');
  
  LoadingManager.setButtonLoading(exportBtn, true);
  LoadingManager.showTopProgress();
  
  try {
    const res = await api('/kb/export', 'POST', {
      // ... 导出参数
    });
    
    if (res.success) {
      showToast('导出成功', 'success');
      // 下载文件
      window.location.href = res.download_url;
    }
  } catch (e) {
    showToast('导出失败: ' + e.message, 'error');
  } finally {
    LoadingManager.setButtonLoading(exportBtn, false);
    LoadingManager.hideTopProgress();
  }
}
```
*/

// ==========================================
// 补丁 10: 标签加载 - 添加加载提示
// ==========================================
// 位置：第 193 行附近
// 函数：async function fetchKBAllTags()

/*
原始代码：
```javascript
async function fetchKBAllTags() {
    try {
        const url = API_BASE + '/kb/tags';
        const resp = await fetch(url, { method: 'GET', credentials: 'same-origin' });
        // ...
    } catch (e) {
        console.error('Failed to load KB tags:', e);
    }
}
```

修改为：
```javascript
async function fetchKBAllTags() {
    LoadingManager.showTopProgress();
    
    try {
        const url = API_BASE + '/kb/tags';
        const resp = await fetch(url, { method: 'GET', credentials: 'same-origin' });
        // ...
    } catch (e) {
        console.error('Failed to load KB tags:', e);
        showToast('加载标签失败', 'error');
    } finally {
        LoadingManager.hideTopProgress();
    }
}
```
*/

// ==========================================
// 使用包装函数的简化方案
// ==========================================

/*
如果不想手动添加 try-finally，可以使用包装函数：

// 方案 1: 包装整个函数
const loadKBDataWithLoading = LoadingManager.withSkeleton(
  'kbTableBody',
  async function() {
    const res = await api('/kb/data');
    renderKBTable(res.data);
  },
  'table',
  5
);

// 调用
await loadKBDataWithLoading();

// 方案 2: 包装 API 调用
const apiWithProgress = LoadingManager.withTopProgress(api);

// 使用
const res = await apiWithProgress('/kb/data');
*/

// ==========================================
// 测试代码
// ==========================================

/*
在浏览器控制台中测试：

// 测试骨架屏
LoadingManager.showSkeleton('kbTableBody', 'table', 5);
setTimeout(() => LoadingManager.hideSkeleton('kbTableBody'), 3000);

// 测试顶部进度条
LoadingManager.showTopProgress();
setTimeout(() => LoadingManager.hideTopProgress(), 3000);

// 测试表格加载遮罩
LoadingManager.showTableLoading('kbTableBody', '加载中...');
setTimeout(() => LoadingManager.hideTableLoading('kbTableBody'), 3000);

// 测试空状态
LoadingManager.showEmptyState('kbTableBody', {
  icon: '📭',
  title: '暂无数据',
  description: '当前没有可显示的内容'
});

// 测试全屏加载
LoadingManager.showFullscreenLoading('处理中...');
setTimeout(() => LoadingManager.hideFullscreenLoading(), 3000);
*/

// ==========================================
// 注意事项
// ==========================================

/*
1. 确保容器元素存在
   - 在调用 LoadingManager 之前检查元素是否存在
   - 使用正确的容器 ID

2. 避免重复显示
   - 同一个容器不要同时显示多个加载状态
   - 使用 finally 确保加载状态被清理

3. 错误处理
   - 始终在 catch 块中显示错误提示
   - 使用空状态提示代替简单的错误消息

4. 性能考虑
   - 骨架屏适合首次加载
   - 刷新数据时使用加载遮罩
   - 快速操作使用顶部进度条

5. 用户体验
   - 加载时间 < 300ms：不显示加载状态
   - 加载时间 300ms-2s：显示加载动画
   - 加载时间 > 2s：显示进度百分比

6. 测试
   - 使用网络节流测试慢速网络
   - 测试快速切换场景
   - 测试错误场景
*/

console.log('✅ 加载状态集成补丁已加载');
console.log('📖 请参考 LOADING_INTEGRATION_GUIDE.md 了解详细使用方法');
