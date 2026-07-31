(function () {
  'use strict';

  var isSubmitting = false;

  function setStatus(message, state) {
    var status = document.getElementById('loginStatus');
    if (!status) return;
    status.textContent = message || '';
    if (state) status.dataset.state = state;
    else delete status.dataset.state;
  }

  async function submitLogin(event) {
    if (event) {
      event.preventDefault();
      // The main bundle binds the same control later; the bootstrap owns this event.
      event.stopImmediatePropagation();
    }
    if (isSubmitting) return;

    var usernameInput = document.getElementById('username');
    var passwordInput = document.getElementById('password');
    var button = document.getElementById('loginBtn');
    var username = usernameInput ? usernameInput.value.trim() : '';
    var password = passwordInput ? passwordInput.value : '';

    if (!username || !password) {
      setStatus('请输入用户名和密码。', 'error');
      (username ? passwordInput : usernameInput)?.focus();
      return;
    }

    isSubmitting = true;
    if (button) {
      button.disabled = true;
      button.textContent = '登录中...';
    }
    setStatus('正在验证登录信息...', 'pending');

    try {
      var response = await fetch('/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ username: username, password: password })
      });
      var data;
      try {
        data = await response.json();
      } catch (_) {
        throw new Error('服务器返回了无法识别的登录响应。');
      }
      if (!response.ok || !data || !data.success) {
        throw new Error((data && data.message) || '用户名或密码不正确。');
      }
      setStatus('登录成功，正在进入工作台...', 'success');
      window.location.reload();
    } catch (error) {
      setStatus(error && error.message ? error.message : '无法连接服务器，请确认后台服务已启动。', 'error');
      if (button) {
        button.disabled = false;
        button.textContent = '登录';
      }
      isSubmitting = false;
    }
  }

  var loginButton = document.getElementById('loginBtn');
  var passwordInput = document.getElementById('password');
  if (loginButton) loginButton.addEventListener('click', submitLogin);
  if (passwordInput) {
    passwordInput.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') submitLogin(event);
    });
  }
}());
