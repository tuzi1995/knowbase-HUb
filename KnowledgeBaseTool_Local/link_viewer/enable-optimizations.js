/**
 * K-Matrix 助手 - 一键启用所有优化功能
 * 
 * 在 index.html 中引入此文件即可自动启用所有优化
 * <script src="enable-optimizations.js"></script>
 */

(function() {
  'use strict';
  
  console.log('🚀 正在启用 K-Matrix 高级优化功能...');
  
  // 等待 DOM 加载完成
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initOptimizations);
  } else {
    initOptimizations();
  }
  
  function initOptimizations() {
    // 检查依赖
    if (typeof KBOptimizations === 'undefined') {
      console.error('❌ 未找到 KBOptimizations，请确保已引入 advanced-optimizations.js');
      return;
    }
    
    // 1. 启用图片懒加载
    try {
      window.lazyLoader = new KBOptimizations.LazyImageLoader({
        rootMargin: '100px',
        threshold: 0.01
      });
      console.log('✅ 图片懒加载已启用');
    } catch (e) {
      console.error('❌ 图片懒加载启用失败:', e);
    }
    
    // 2. 启用搜索功能增强
    try {
      window.searchEnhancer = new KBOptimizations.SearchEnhancer({
        maxHistory: 10,
        storageKey: 'kb_search_history',
        highlightColor: '#ffeb3b'
      });
      
      // 为所有搜索框添加历史记录
      const searchInputs = document.querySelectorAll('input[type="text"][placeholder*="搜索"], input[type="search"]');
      searchInputs.forEach(input => {
        try {
          window.searchEnhancer.createHistoryDropdown(input, (query) => {
            input.value = query;
            // 触发input事件
            input.dispatchEvent(new Event('input', { bubbles: true }));
          });
        } catch (e) {
          console.warn('搜索框历史记录添加失败:', input.id, e);
        }
      });
      
      console.log(`✅ 搜索功能增强已启用 (${searchInputs.length} 个搜索框)`);
    } catch (e) {
      console.error('❌ 搜索功能增强启用失败:', e);
    }
    
    // 3. 启用响应式布局
    try {
      setupResponsiveLayout();
      console.log('✅ 响应式布局已启用');
    } catch (e) {
      console.error('❌ 响应式布局启用失败:', e);
    }
    
    // 4. 监听编辑对话框，启用自动保存
    try {
      setupAutoSave();
      console.log('✅ 自动保存草稿已配置');
    } catch (e) {
      console.error('❌ 自动保存草稿配置失败:', e);
    }
    
    console.log('🎉 所有优化功能已启用！');
  }
  
  // 设置响应式布局
  function setupResponsiveLayout() {
    // 检测屏幕尺寸
    function isMobile() {
      return window.innerWidth < 768;
    }
    
    // 创建移动端Tab选择器
    function createMobileTabSelector() {
      const navTabs = document.querySelector('.nav-tabs');
      if (!navTabs) return;
      
      // 检查是否已存在
      if (document.querySelector('.mobile-tab-selector')) return;
      
      const select = document.createElement('select');
      select.className = 'mobile-tab-selector';
      select.style.display = 'none';
      
      // 从Tab导航中提取选项
      const tabs = navTabs.querySelectorAll('.nav-link');
      tabs.forEach((tab, index) => {
        const option = document.createElement('option');
        option.value = tab.dataset.tab || index;
        option.textContent = tab.textContent.trim();
        if (tab.classList.contains('active')) {
          option.selected = true;
        }
        select.appendChild(option);
      });
      
      // 插入到Tab导航后面
      navTabs.parentNode.insertBefore(select, navTabs.nextSibling);
      
      // 监听选择变化
      select.addEventListener('change', function() {
        const value = this.value;
        const tab = document.querySelector(`.nav-link[data-tab="${value}"]`);
        if (tab) {
          tab.click();
        }
      });
    }
    
    // 更新显示模式
    function updateViewMode() {
      const mobile = isMobile();
      
      // 切换Tab导航
      const navTabs = document.querySelector('.nav-tabs');
      const mobileSelector = document.querySelector('.mobile-tab-selector');
      
      if (navTabs) {
        navTabs.style.display = mobile ? 'none' : '';
      }
      
      if (mobileSelector) {
        mobileSelector.style.display = mobile ? 'block' : 'none';
      }
      
      // 更新body类
      if (mobile) {
        document.body.classList.add('mobile-view');
      } else {
        document.body.classList.remove('mobile-view');
      }
    }
    
    // 初始化
    createMobileTabSelector();
    updateViewMode();
    
    // 监听窗口大小变化
    let resizeTimer;
    window.addEventListener('resize', function() {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(updateViewMode, 300);
    });
  }
  
  // 设置自动保存
  function setupAutoSave() {
    // 查找编辑对话框
    const editModal = document.getElementById('editModal') || document.querySelector('.modal');
    if (!editModal) {
      console.warn('未找到编辑对话框，自动保存功能将在对话框打开时启用');
      return;
    }
    
    let autoSave = null;
    
    // 监听对话框显示
    const observer = new MutationObserver(function(mutations) {
      mutations.forEach(function(mutation) {
        if (mutation.attributeName === 'class' || mutation.attributeName === 'style') {
          const isVisible = editModal.classList.contains('show') || 
                           editModal.style.display === 'block';
          
          if (isVisible && !autoSave) {
            // 对话框打开，启动自动保存
            const fields = [];
            
            // 查找所有输入字段
            const inputs = editModal.querySelectorAll('input[type="text"], textarea, select');
            inputs.forEach(input => {
              if (input.id) {
                fields.push('#' + input.id);
              }
            });
            
            if (fields.length > 0) {
              autoSave = new KBOptimizations.AutoSaveDraft({
                interval: 30000,
                storageKey: 'kb_edit_draft',
                fields: fields,
                onSave: function(draft) {
                  console.log('✅ 草稿已自动保存');
                },
                onRestore: function(draft) {
                  console.log('✅ 草稿已恢复');
                }
              });
              
              autoSave.init();
              console.log('✅ 自动保存已启动');
            }
          } else if (!isVisible && autoSave) {
            // 对话框关闭，停止自动保存
            autoSave.stopAutoSave();
            autoSave = null;
            console.log('⏸️  自动保存已停止');
          }
        }
      });
    });
    
    observer.observe(editModal, {
      attributes: true,
      attributeFilter: ['class', 'style']
    });
  }
  
  // 导出工具函数
  window.KBOptimizationsHelper = {
    // 刷新图片懒加载
    refreshLazyImages: function() {
      if (window.lazyLoader) {
        window.lazyLoader.refresh();
        console.log('✅ 图片懒加载已刷新');
      }
    },
    
    // 添加搜索历史
    addSearchHistory: function(query) {
      if (window.searchEnhancer && query) {
        window.searchEnhancer.addToHistory(query);
      }
    },
    
    // 高亮搜索结果
    highlightSearchResults: function(query, container) {
      if (window.searchEnhancer && query) {
        const element = container || document.body;
        window.searchEnhancer.highlightInElement(element, query);
      }
    },
    
    // 清除高亮
    clearHighlight: function(container) {
      if (window.searchEnhancer) {
        const element = container || document.body;
        window.searchEnhancer.removeHighlight(element);
      }
    },
    
    // 手动保存草稿
    saveDraft: function() {
      if (window.autoSave) {
        window.autoSave.saveDraft();
      }
    },
    
    // 清除草稿
    clearDraft: function() {
      if (window.autoSave) {
        window.autoSave.clearDraft();
      }
    }
  };
  
})();
