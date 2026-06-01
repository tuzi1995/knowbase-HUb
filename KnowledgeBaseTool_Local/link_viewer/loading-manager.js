/**
 * ==========================================
 * 加载状态管理器
 * ==========================================
 * 
 * 功能：
 * 1. 统一管理所有加载状态
 * 2. 提供多种加载提示方式
 * 3. 自动处理加载状态的显示和隐藏
 * 4. 支持嵌套加载状态
 * 
 * 使用示例：
 * 
 * // 1. 顶部进度条
 * LoadingManager.showTopProgress();
 * await fetchData();
 * LoadingManager.hideTopProgress();
 * 
 * // 2. 表格加载遮罩
 * LoadingManager.showTableLoading('kbTableBody', '加载中...');
 * await loadKBData();
 * LoadingManager.hideTableLoading('kbTableBody');
 * 
 * // 3. 骨架屏
 * LoadingManager.showSkeleton('kbTableBody', 'table', 5);
 * await loadKBData();
 * LoadingManager.hideSkeleton('kbTableBody');
 * 
 * // 4. 按钮加载状态
 * LoadingManager.setButtonLoading(button, true);
 * await saveData();
 * LoadingManager.setButtonLoading(button, false);
 * 
 * 优化：2026-04-22
 */

const LoadingManager = {
  // 存储加载状态
  _loadingStates: new Map(),
  _topProgressBar: null,
  _loadingCount: 0,

  /**
   * 初始化加载管理器
   */
  init() {
    console.log('✅ 加载状态管理器已初始化');
  },

  /**
   * 显示顶部进度条
   */
  showTopProgress() {
    if (!this._topProgressBar) {
      this._topProgressBar = document.createElement('div');
      this._topProgressBar.className = 'top-progress-bar';
      document.body.appendChild(this._topProgressBar);
    }
    this._topProgressBar.style.display = 'block';
    this._loadingCount++;
  },

  /**
   * 隐藏顶部进度条
   */
  hideTopProgress() {
    this._loadingCount = Math.max(0, this._loadingCount - 1);
    if (this._loadingCount === 0 && this._topProgressBar) {
      this._topProgressBar.style.display = 'none';
    }
  },

  /**
   * 显示表格加载遮罩
   * @param {string} containerId - 容器ID
   * @param {string} message - 加载提示文字
   * @param {boolean} transparent - 是否透明背景
   */
  showTableLoading(containerId, message = '加载中...', transparent = false) {
    const container = document.getElementById(containerId);
    if (!container) {
      console.warn(`Container not found: ${containerId}`);
      return;
    }

    // 检查是否已存在加载遮罩
    let overlay = container.querySelector('.table-loading-overlay');
    if (overlay) return;

    // 创建加载遮罩
    overlay = document.createElement('div');
    overlay.className = 'table-loading-overlay';
    if (transparent) overlay.classList.add('transparent');

    overlay.innerHTML = `
      <div class="loading-content">
        <div class="loading-spinner"></div>
        <div class="loading-text">${this._escapeHtml(message)}</div>
      </div>
    `;

    // 设置容器为相对定位
    const position = window.getComputedStyle(container).position;
    if (position === 'static') {
      container.style.position = 'relative';
    }

    container.appendChild(overlay);
    this._loadingStates.set(containerId, { type: 'overlay', element: overlay });

    // 添加淡入动画
    requestAnimationFrame(() => {
      overlay.style.opacity = '1';
    });
  },

  /**
   * 隐藏表格加载遮罩
   * @param {string} containerId - 容器ID
   */
  hideTableLoading(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const overlay = container.querySelector('.table-loading-overlay');
    if (overlay) {
      overlay.style.opacity = '0';
      setTimeout(() => {
        overlay.remove();
        this._loadingStates.delete(containerId);
      }, 300);
    }
  },

  /**
   * 显示骨架屏
   * @param {string} containerId - 容器ID
   * @param {string} type - 骨架屏类型: 'table', 'card', 'list'
   * @param {number} count - 显示数量
   */
  showSkeleton(containerId, type = 'table', count = 5) {
    const container = document.getElementById(containerId);
    if (!container) {
      console.warn(`Container not found: ${containerId}`);
      return;
    }

    // 清空容器
    container.innerHTML = '';

    // 生成骨架屏
    const skeletonHTML = this._generateSkeleton(type, count);
    container.innerHTML = skeletonHTML;

    this._loadingStates.set(containerId, { type: 'skeleton' });
  },

  /**
   * 隐藏骨架屏
   * @param {string} containerId - 容器ID
   */
  hideSkeleton(containerId) {
    const container = document.getElementById(containerId);
    if (!container) return;

    // 骨架屏会在数据加载后被替换，这里只是清理状态
    this._loadingStates.delete(containerId);
  },

  /**
   * 生成骨架屏HTML
   * @param {string} type - 类型
   * @param {number} count - 数量
   * @returns {string} HTML字符串
   */
  _generateSkeleton(type, count) {
    if (type === 'table') {
      return this._generateTableSkeleton(count);
    } else if (type === 'card') {
      return this._generateCardSkeleton(count);
    } else if (type === 'list') {
      return this._generateListSkeleton(count);
    }
    return '';
  },

  /**
   * 生成表格骨架屏
   */
  _generateTableSkeleton(count) {
    let html = '';
    for (let i = 0; i < count; i++) {
      html += `
        <tr class="skeleton-table-row fade-in" style="animation-delay: ${i * 0.05}s">
          <td style="width: 50px;"><div class="skeleton skeleton-text" style="width: 20px;"></div></td>
          <td style="width: 80px;"><div class="skeleton skeleton-text"></div></td>
          <td style="width: 120px;"><div class="skeleton skeleton-text"></div></td>
          <td style="width: 200px;"><div class="skeleton skeleton-text medium"></div></td>
          <td><div class="skeleton skeleton-text short"></div></td>
          <td style="width: 150px;"><div class="skeleton skeleton-text"></div></td>
          <td style="width: 100px;"><div class="skeleton skeleton-text"></div></td>
        </tr>
      `;
    }
    return html;
  },

  /**
   * 生成卡片骨架屏
   */
  _generateCardSkeleton(count) {
    let html = '';
    for (let i = 0; i < count; i++) {
      html += `
        <div class="card-skeleton fade-in" style="animation-delay: ${i * 0.05}s">
          <div class="card-skeleton-header">
            <div class="skeleton skeleton-avatar"></div>
            <div style="flex: 1;">
              <div class="skeleton skeleton-text" style="width: 40%; margin-bottom: 8px;"></div>
              <div class="skeleton skeleton-text" style="width: 60%;"></div>
            </div>
          </div>
          <div class="card-skeleton-body">
            <div class="skeleton skeleton-text"></div>
            <div class="skeleton skeleton-text medium"></div>
            <div class="skeleton skeleton-text short"></div>
          </div>
        </div>
      `;
    }
    return html;
  },

  /**
   * 生成列表骨架屏
   */
  _generateListSkeleton(count) {
    let html = '';
    for (let i = 0; i < count; i++) {
      html += `
        <div class="skeleton-table-row fade-in" style="animation-delay: ${i * 0.05}s">
          <div class="skeleton skeleton-text"></div>
          <div class="skeleton skeleton-text medium"></div>
        </div>
      `;
    }
    return html;
  },

  /**
   * 设置按钮加载状态
   * @param {HTMLElement} button - 按钮元素
   * @param {boolean} loading - 是否加载中
   * @param {string} loadingText - 加载中的文字（可选）
   */
  setButtonLoading(button, loading, loadingText = null) {
    if (!button) return;

    if (loading) {
      button.disabled = true;
      button.classList.add('loading');
      if (loadingText) {
        button.dataset.originalText = button.textContent;
        button.textContent = loadingText;
      }
    } else {
      button.disabled = false;
      button.classList.remove('loading');
      if (button.dataset.originalText) {
        button.textContent = button.dataset.originalText;
        delete button.dataset.originalText;
      }
    }
  },

  /**
   * 显示内联加载状态
   * @param {string} containerId - 容器ID
   * @param {string} message - 提示文字
   */
  showInlineLoading(containerId, message = '加载中...') {
    const container = document.getElementById(containerId);
    if (!container) return;

    const loadingHTML = `
      <div class="inline-loading fade-in">
        <div class="loading-spinner small"></div>
        <span>${this._escapeHtml(message)}</span>
      </div>
    `;

    container.innerHTML = loadingHTML;
    this._loadingStates.set(containerId, { type: 'inline' });
  },

  /**
   * 显示空状态
   * @param {string} containerId - 容器ID
   * @param {Object} options - 配置选项
   */
  showEmptyState(containerId, options = {}) {
    const container = document.getElementById(containerId);
    if (!container) return;

    const {
      icon = '📭',
      title = '暂无数据',
      description = '当前没有可显示的内容',
      actionText = null,
      onAction = null
    } = options;

    let actionHTML = '';
    if (actionText && onAction) {
      const actionId = `empty-action-${Date.now()}`;
      actionHTML = `
        <div class="empty-state-action">
          <button id="${actionId}">${this._escapeHtml(actionText)}</button>
        </div>
      `;
      
      // 延迟绑定事件，确保元素已插入DOM
      setTimeout(() => {
        const btn = document.getElementById(actionId);
        if (btn) btn.addEventListener('click', onAction);
      }, 0);
    }

    const emptyHTML = `
      <div class="empty-state fade-in">
        <div class="empty-state-icon">${icon}</div>
        <div class="empty-state-title">${this._escapeHtml(title)}</div>
        <div class="empty-state-description">${this._escapeHtml(description)}</div>
        ${actionHTML}
      </div>
    `;

    container.innerHTML = emptyHTML;
  },

  /**
   * 显示全屏加载遮罩
   * @param {string} message - 提示文字
   */
  showFullscreenLoading(message = '加载中...') {
    let overlay = document.getElementById('fullscreen-loading-overlay');
    if (overlay) return;

    overlay = document.createElement('div');
    overlay.id = 'fullscreen-loading-overlay';
    overlay.className = 'loading-overlay fullscreen';
    overlay.innerHTML = `
      <div class="loading-content">
        <div class="loading-spinner large"></div>
        <div class="loading-text">${this._escapeHtml(message)}</div>
      </div>
    `;

    document.body.appendChild(overlay);
    requestAnimationFrame(() => {
      overlay.style.opacity = '1';
    });
  },

  /**
   * 隐藏全屏加载遮罩
   */
  hideFullscreenLoading() {
    const overlay = document.getElementById('fullscreen-loading-overlay');
    if (overlay) {
      overlay.style.opacity = '0';
      setTimeout(() => overlay.remove(), 300);
    }
  },

  /**
   * 包装异步函数，自动显示/隐藏顶部进度条
   * @param {Function} asyncFn - 异步函数
   * @returns {Function} 包装后的函数
   */
  withTopProgress(asyncFn) {
    return async (...args) => {
      this.showTopProgress();
      try {
        return await asyncFn(...args);
      } finally {
        this.hideTopProgress();
      }
    };
  },

  /**
   * 包装异步函数，自动显示/隐藏表格加载状态
   * @param {string} containerId - 容器ID
   * @param {Function} asyncFn - 异步函数
   * @param {string} message - 加载提示
   * @returns {Function} 包装后的函数
   */
  withTableLoading(containerId, asyncFn, message = '加载中...') {
    return async (...args) => {
      this.showTableLoading(containerId, message);
      try {
        return await asyncFn(...args);
      } finally {
        this.hideTableLoading(containerId);
      }
    };
  },

  /**
   * 包装异步函数，自动显示/隐藏骨架屏
   * @param {string} containerId - 容器ID
   * @param {Function} asyncFn - 异步函数
   * @param {string} type - 骨架屏类型
   * @param {number} count - 数量
   * @returns {Function} 包装后的函数
   */
  withSkeleton(containerId, asyncFn, type = 'table', count = 5) {
    return async (...args) => {
      this.showSkeleton(containerId, type, count);
      try {
        return await asyncFn(...args);
      } finally {
        this.hideSkeleton(containerId);
      }
    };
  },

  /**
   * 清理所有加载状态
   */
  clearAll() {
    this.hideTopProgress();
    this.hideFullscreenLoading();
    
    this._loadingStates.forEach((state, containerId) => {
      if (state.type === 'overlay') {
        this.hideTableLoading(containerId);
      } else if (state.type === 'skeleton') {
        this.hideSkeleton(containerId);
      }
    });
    
    this._loadingStates.clear();
    this._loadingCount = 0;
  },

  /**
   * HTML转义
   */
  _escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
  }
};

// 初始化
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => LoadingManager.init());
} else {
  LoadingManager.init();
}

// 导出到全局
window.LoadingManager = LoadingManager;
