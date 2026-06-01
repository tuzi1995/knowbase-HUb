/**
 * K-Matrix 助手 - 高级优化功能
 * 
 * 包含功能：
 * 1. 图片懒加载
 * 2. 搜索功能增强（搜索历史、结果高亮）
 * 3. 自动保存草稿
 * 
 * 使用方法：
 * 在 index.html 中引入此文件
 * <script src="advanced-optimizations.js"></script>
 */

(function() {
  'use strict';

  // ============================================
  // 1. 图片懒加载
  // ============================================
  
  class LazyImageLoader {
    constructor(options = {}) {
      this.options = {
        rootMargin: options.rootMargin || '50px',
        threshold: options.threshold || 0.01,
        loadingClass: options.loadingClass || 'lazy-loading',
        loadedClass: options.loadedClass || 'lazy-loaded',
        errorClass: options.errorClass || 'lazy-error',
        placeholder: options.placeholder || 'data:image/svg+xml,%3Csvg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 300"%3E%3Crect fill="%23f0f0f0" width="400" height="300"/%3E%3Ctext x="50%25" y="50%25" text-anchor="middle" fill="%23999" font-size="18"%3E加载中...%3C/text%3E%3C/svg%3E'
      };
      
      this.observer = null;
      this.init();
    }
    
    init() {
      if (!('IntersectionObserver' in window)) {
        console.warn('浏览器不支持 IntersectionObserver，图片懒加载已禁用');
        this.loadAllImages();
        return;
      }
      
      this.observer = new IntersectionObserver(
        this.handleIntersection.bind(this),
        {
          rootMargin: this.options.rootMargin,
          threshold: this.options.threshold
        }
      );
      
      this.observeImages();
    }
    
    observeImages() {
      const images = document.querySelectorAll('img[data-src], img[data-lazy]');
      images.forEach(img => {
        // 设置占位图
        if (!img.src || img.src === window.location.href) {
          img.src = this.options.placeholder;
        }
        img.classList.add(this.options.loadingClass);
        this.observer.observe(img);
      });
    }
    
    handleIntersection(entries) {
      entries.forEach(entry => {
        if (entry.isIntersecting) {
          this.loadImage(entry.target);
          this.observer.unobserve(entry.target);
        }
      });
    }
    
    loadImage(img) {
      const src = img.dataset.src || img.dataset.lazy;
      if (!src) return;
      
      const tempImg = new Image();
      
      tempImg.onload = () => {
        img.src = src;
        img.classList.remove(this.options.loadingClass);
        img.classList.add(this.options.loadedClass);
        
        // 淡入动画
        img.style.opacity = '0';
        img.style.transition = 'opacity 0.3s ease-in';
        setTimeout(() => {
          img.style.opacity = '1';
        }, 10);
      };
      
      tempImg.onerror = () => {
        img.classList.remove(this.options.loadingClass);
        img.classList.add(this.options.errorClass);
        img.alt = '图片加载失败';
      };
      
      tempImg.src = src;
    }
    
    loadAllImages() {
      // 降级方案：直接加载所有图片
      const images = document.querySelectorAll('img[data-src], img[data-lazy]');
      images.forEach(img => {
        const src = img.dataset.src || img.dataset.lazy;
        if (src) {
          img.src = src;
        }
      });
    }
    
    refresh() {
      // 刷新观察器，用于动态添加的图片
      if (this.observer) {
        this.observeImages();
      }
    }
    
    destroy() {
      if (this.observer) {
        this.observer.disconnect();
      }
    }
  }
  
  // ============================================
  // 2. 搜索功能增强
  // ============================================
  
  class SearchEnhancer {
    constructor(options = {}) {
      this.options = {
        maxHistory: options.maxHistory || 10,
        storageKey: options.storageKey || 'kb_search_history',
        highlightClass: options.highlightClass || 'search-highlight',
        highlightColor: options.highlightColor || '#ffeb3b'
      };
      
      this.history = this.loadHistory();
    }
    
    // 加载搜索历史
    loadHistory() {
      try {
        const stored = localStorage.getItem(this.options.storageKey);
        return stored ? JSON.parse(stored) : [];
      } catch (e) {
        console.error('加载搜索历史失败:', e);
        return [];
      }
    }
    
    // 保存搜索历史
    saveHistory() {
      try {
        localStorage.setItem(this.options.storageKey, JSON.stringify(this.history));
      } catch (e) {
        console.error('保存搜索历史失败:', e);
      }
    }
    
    // 添加搜索记录
    addToHistory(query) {
      if (!query || !query.trim()) return;
      
      query = query.trim();
      
      // 移除重复项
      this.history = this.history.filter(item => item.query !== query);
      
      // 添加到开头
      this.history.unshift({
        query: query,
        timestamp: Date.now()
      });
      
      // 限制数量
      if (this.history.length > this.options.maxHistory) {
        this.history = this.history.slice(0, this.options.maxHistory);
      }
      
      this.saveHistory();
    }
    
    // 获取搜索历史
    getHistory() {
      return this.history;
    }
    
    // 清空搜索历史
    clearHistory() {
      this.history = [];
      this.saveHistory();
    }
    
    // 高亮搜索结果
    highlightText(text, query) {
      if (!text || !query) return text;
      
      const regex = new RegExp(`(${this.escapeRegex(query)})`, 'gi');
      return text.replace(regex, `<mark class="${this.options.highlightClass}" style="background-color: ${this.options.highlightColor}; padding: 2px 4px; border-radius: 2px;">$1</mark>`);
    }
    
    // 转义正则表达式特殊字符
    escapeRegex(str) {
      return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    }
    
    // 在DOM中高亮文本
    highlightInElement(element, query) {
      if (!element || !query) return;
      
      const walker = document.createTreeWalker(
        element,
        NodeFilter.SHOW_TEXT,
        null,
        false
      );
      
      const nodesToReplace = [];
      let node;
      
      while (node = walker.nextNode()) {
        if (node.nodeValue.toLowerCase().includes(query.toLowerCase())) {
          nodesToReplace.push(node);
        }
      }
      
      nodesToReplace.forEach(node => {
        const span = document.createElement('span');
        span.innerHTML = this.highlightText(node.nodeValue, query);
        node.parentNode.replaceChild(span, node);
      });
    }
    
    // 移除高亮
    removeHighlight(element) {
      if (!element) return;
      
      const highlights = element.querySelectorAll(`.${this.options.highlightClass}`);
      highlights.forEach(mark => {
        const text = document.createTextNode(mark.textContent);
        mark.parentNode.replaceChild(text, mark);
      });
    }
    
    // 创建搜索历史下拉框
    createHistoryDropdown(inputElement, onSelect) {
      const dropdown = document.createElement('div');
      dropdown.className = 'search-history-dropdown';
      dropdown.style.cssText = `
        position: absolute;
        top: 100%;
        left: 0;
        right: 0;
        background: white;
        border: 1px solid #ddd;
        border-top: none;
        border-radius: 0 0 4px 4px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        max-height: 300px;
        overflow-y: auto;
        z-index: 1000;
        display: none;
      `;
      
      const updateDropdown = () => {
        dropdown.innerHTML = '';
        
        if (this.history.length === 0) {
          dropdown.style.display = 'none';
          return;
        }
        
        // 添加标题
        const header = document.createElement('div');
        header.style.cssText = `
          padding: 8px 12px;
          background: #f5f5f5;
          border-bottom: 1px solid #ddd;
          font-size: 12px;
          color: #666;
          display: flex;
          justify-content: space-between;
          align-items: center;
        `;
        header.innerHTML = `
          <span>搜索历史</span>
          <button class="clear-history-btn" style="background: none; border: none; color: #1890ff; cursor: pointer; font-size: 12px;">清空</button>
        `;
        dropdown.appendChild(header);
        
        // 添加历史记录
        this.history.forEach(item => {
          const itemEl = document.createElement('div');
          itemEl.className = 'history-item';
          itemEl.style.cssText = `
            padding: 8px 12px;
            cursor: pointer;
            border-bottom: 1px solid #f0f0f0;
            display: flex;
            justify-content: space-between;
            align-items: center;
          `;
          itemEl.innerHTML = `
            <span style="flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${this.escapeHtml(item.query)}</span>
            <span style="font-size: 11px; color: #999; margin-left: 8px;">${this.formatTime(item.timestamp)}</span>
          `;
          
          itemEl.addEventListener('mouseenter', () => {
            itemEl.style.background = '#f5f5f5';
          });
          
          itemEl.addEventListener('mouseleave', () => {
            itemEl.style.background = 'white';
          });
          
          itemEl.addEventListener('click', () => {
            if (onSelect) {
              onSelect(item.query);
            }
            dropdown.style.display = 'none';
          });
          
          dropdown.appendChild(itemEl);
        });
        
        // 清空按钮事件
        const clearBtn = header.querySelector('.clear-history-btn');
        clearBtn.addEventListener('click', (e) => {
          e.stopPropagation();
          this.clearHistory();
          updateDropdown();
        });
        
        dropdown.style.display = 'block';
      };
      
      // 输入框获得焦点时显示
      inputElement.addEventListener('focus', () => {
        updateDropdown();
      });
      
      // 点击外部时隐藏
      document.addEventListener('click', (e) => {
        if (!inputElement.contains(e.target) && !dropdown.contains(e.target)) {
          dropdown.style.display = 'none';
        }
      });
      
      // 插入到输入框后面
      inputElement.parentNode.style.position = 'relative';
      inputElement.parentNode.appendChild(dropdown);
      
      return dropdown;
    }
    
    // 转义HTML
    escapeHtml(str) {
      const div = document.createElement('div');
      div.textContent = str;
      return div.innerHTML;
    }
    
    // 格式化时间
    formatTime(timestamp) {
      const now = Date.now();
      const diff = now - timestamp;
      
      if (diff < 60000) return '刚刚';
      if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
      if (diff < 86400000) return `${Math.floor(diff / 3600000)}小时前`;
      if (diff < 604800000) return `${Math.floor(diff / 86400000)}天前`;
      
      const date = new Date(timestamp);
      return `${date.getMonth() + 1}/${date.getDate()}`;
    }
  }
  
  // ============================================
  // 3. 自动保存草稿
  // ============================================
  
  class AutoSaveDraft {
    constructor(options = {}) {
      this.options = {
        interval: options.interval || 30000, // 30秒
        storageKey: options.storageKey || 'kb_draft',
        fields: options.fields || [], // 要监听的字段选择器
        onSave: options.onSave || null,
        onRestore: options.onRestore || null
      };
      
      this.timer = null;
      this.isDirty = false;
      this.lastSaveTime = null;
    }
    
    // 初始化
    init() {
      this.setupListeners();
      this.restoreDraft();
      this.startAutoSave();
    }
    
    // 设置监听器
    setupListeners() {
      this.options.fields.forEach(selector => {
        const elements = document.querySelectorAll(selector);
        elements.forEach(el => {
          el.addEventListener('input', () => {
            this.isDirty = true;
          });
          
          el.addEventListener('change', () => {
            this.isDirty = true;
          });
        });
      });
    }
    
    // 开始自动保存
    startAutoSave() {
      this.timer = setInterval(() => {
        if (this.isDirty) {
          this.saveDraft();
        }
      }, this.options.interval);
    }
    
    // 停止自动保存
    stopAutoSave() {
      if (this.timer) {
        clearInterval(this.timer);
        this.timer = null;
      }
    }
    
    // 保存草稿
    saveDraft() {
      const draft = {};
      let hasData = false;
      
      this.options.fields.forEach(selector => {
        const elements = document.querySelectorAll(selector);
        elements.forEach(el => {
          const key = el.id || el.name || selector;
          const value = el.value || el.textContent;
          
          if (value && value.trim()) {
            draft[key] = value;
            hasData = true;
          }
        });
      });
      
      if (!hasData) return;
      
      try {
        const draftData = {
          data: draft,
          timestamp: Date.now(),
          url: window.location.href
        };
        
        localStorage.setItem(this.options.storageKey, JSON.stringify(draftData));
        this.isDirty = false;
        this.lastSaveTime = Date.now();
        
        // 显示保存提示
        this.showSaveNotification();
        
        if (this.options.onSave) {
          this.options.onSave(draft);
        }
        
        console.log('✅ 草稿已自动保存', new Date().toLocaleTimeString());
      } catch (e) {
        console.error('保存草稿失败:', e);
      }
    }
    
    // 恢复草稿
    restoreDraft() {
      try {
        const stored = localStorage.getItem(this.options.storageKey);
        if (!stored) return false;
        
        const draftData = JSON.parse(stored);
        
        // 检查是否是当前页面的草稿
        if (draftData.url !== window.location.href) {
          return false;
        }
        
        // 检查草稿是否过期（24小时）
        const age = Date.now() - draftData.timestamp;
        if (age > 86400000) {
          this.clearDraft();
          return false;
        }
        
        // 询问用户是否恢复
        const timeAgo = this.formatTimeAgo(age);
        const shouldRestore = confirm(`发现 ${timeAgo} 的草稿，是否恢复？`);
        
        if (shouldRestore) {
          Object.keys(draftData.data).forEach(key => {
            const el = document.getElementById(key) || document.querySelector(`[name="${key}"]`);
            if (el) {
              if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT') {
                el.value = draftData.data[key];
              } else {
                el.textContent = draftData.data[key];
              }
              
              // 触发change事件
              el.dispatchEvent(new Event('change', { bubbles: true }));
            }
          });
          
          if (this.options.onRestore) {
            this.options.onRestore(draftData.data);
          }
          
          console.log('✅ 草稿已恢复');
          return true;
        } else {
          this.clearDraft();
          return false;
        }
      } catch (e) {
        console.error('恢复草稿失败:', e);
        return false;
      }
    }
    
    // 清除草稿
    clearDraft() {
      try {
        localStorage.removeItem(this.options.storageKey);
        this.isDirty = false;
        console.log('✅ 草稿已清除');
      } catch (e) {
        console.error('清除草稿失败:', e);
      }
    }
    
    // 显示保存通知
    showSaveNotification() {
      const notification = document.createElement('div');
      notification.className = 'auto-save-notification';
      notification.textContent = '✓ 草稿已保存';
      notification.style.cssText = `
        position: fixed;
        bottom: 20px;
        right: 20px;
        background: #52c41a;
        color: white;
        padding: 12px 20px;
        border-radius: 4px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15);
        z-index: 10000;
        font-size: 14px;
        opacity: 0;
        transition: opacity 0.3s ease-in-out;
      `;
      
      document.body.appendChild(notification);
      
      setTimeout(() => {
        notification.style.opacity = '1';
      }, 10);
      
      setTimeout(() => {
        notification.style.opacity = '0';
        setTimeout(() => {
          document.body.removeChild(notification);
        }, 300);
      }, 2000);
    }
    
    // 格式化时间差
    formatTimeAgo(ms) {
      const seconds = Math.floor(ms / 1000);
      const minutes = Math.floor(seconds / 60);
      const hours = Math.floor(minutes / 60);
      
      if (hours > 0) return `${hours}小时前`;
      if (minutes > 0) return `${minutes}分钟前`;
      return `${seconds}秒前`;
    }
    
    // 销毁
    destroy() {
      this.stopAutoSave();
    }
  }
  
  // ============================================
  // 导出到全局
  // ============================================
  
  window.KBOptimizations = {
    LazyImageLoader,
    SearchEnhancer,
    AutoSaveDraft
  };
  
  console.log('✅ K-Matrix 高级优化功能已加载');
  
})();
