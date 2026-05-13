const API = 'https://stock-analysis-i3xj.onrender.com';

async function checkAuth() {
  const token = localStorage.getItem('kr_stock_token');
  if (!token) { showLogin(); return; }
  try {
    const res = await fetch(`${API}/api/auth/verify?token=${token}`);
    if (!res.ok) { localStorage.removeItem('kr_stock_token'); showLogin(); }
  } catch {
    showLogin();
  }
}

function showLogin() {
  document.getElementById('auth-overlay').style.display = 'flex';
  document.body.style.overflow = 'hidden';
}

function hideLogin() {
  document.getElementById('auth-overlay').style.display = 'none';
  document.body.style.overflow = '';
}

async function submitLogin() {
  const pw = document.getElementById('auth-pw').value;
  const errEl = document.getElementById('auth-error');
  if (!pw) return;

  const btn = document.getElementById('auth-btn');
  btn.disabled = true;
  btn.textContent = '확인 중...';

  try {
    const res = await fetch(`${API}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: pw }),
    });
    if (res.ok) {
      const { token } = await res.json();
      localStorage.setItem('kr_stock_token', token);
      hideLogin();
    } else {
      errEl.textContent = '비밀번호가 틀렸습니다';
      document.getElementById('auth-pw').value = '';
      document.getElementById('auth-pw').focus();
    }
  } catch {
    errEl.textContent = '서버에 연결할 수 없습니다';
  } finally {
    btn.disabled = false;
    btn.textContent = '입장';
  }
}

document.addEventListener('DOMContentLoaded', () => {
  checkAuth();
  document.getElementById('auth-pw').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') submitLogin();
  });
});
