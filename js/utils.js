/* ==============================
   Utils — Supabase Integration, Session, CSV Export
   ============================== */

// Supabase Configuration
const SUPABASE_URL = 'https://voqpifhgvizudlggsuzj.supabase.co';
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZvcXBpZmhndml6dWRsZ2dzdXpqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE3ODIzNzYsImV4cCI6MjA4NzM1ODM3Nn0.B88w3JCAv75qIky638UwPh6TVyKfYbAxHyCB2zdSe2o';
let supabaseClient = null;

// Backend API URL (Render)
const API_BASE_URL = window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
  ? 'http://localhost:3001'
  : 'https://asr-services-backend.onrender.com';

// Initialize Supabase client if SDK is present
if (window.supabase && window.supabase.createClient) {
  supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
}



const Utils = {
  /* ---------- Rate Limiter ---------- */
  rateLimit(key, maxAttempts, windowMs) {
    const now = Date.now();
    const data = JSON.parse(localStorage.getItem(`rl_${key}`) || '{"attempts":[],"blocked":0}');

    if (data.blocked && now < data.blocked) {
      return false;
    }

    data.attempts = data.attempts.filter(t => now - t < windowMs);
    if (data.attempts.length >= maxAttempts) {
      data.blocked = now + 60000;
      localStorage.setItem(`rl_${key}`, JSON.stringify(data));
      return false;
    }

    data.attempts.push(now);
    localStorage.setItem(`rl_${key}`, JSON.stringify(data));
    return true;
  },

  /* ---------- Session Helpers ---------- */
  async getSession() {
    const { data: { session } } = await supabaseClient.auth.getSession();
    if (!session) return null;

    // Get profile data
    const { data: profile } = await supabaseClient
      .from('profiles')
      .select('*')
      .eq('email', session.user.email)
      .single();

    return { ...session.user, ...profile };
  },

  async setSession(data) {
    // Sync local metadata
    const existing = JSON.parse(sessionStorage.getItem('rs_session') || '{}');
    sessionStorage.setItem('rs_session', JSON.stringify({ ...existing, ...data }));
  },

  async clearSession() {
    await supabaseClient.auth.signOut();
  },

  async isLoggedIn() {
    const s = await this.getSession();
    return !!s;
  },

  async isPaid() {
    const s = await this.getSession();
    if (!s || !s.is_paid) return false;
    return true;
  },


  async hasUsedBatch() {
    const sessionData = JSON.parse(sessionStorage.getItem('rs_session') || '{}');
    if (sessionData.batchUsed === true) return true;

    const s = await this.getSession();
    return s && s.batchUsed === true;
  },

  async markBatchUsed() {
    await this.setSession({ batchUsed: true });
  },

  /* ---------- Auth & Payment Logic ---------- */
  validateEmail(email) {
    return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
  },

  async signInWithGoogle() {
    const { data, error } = await supabaseClient.auth.signInWithOAuth({
      provider: 'google',
      options: {
        redirectTo: window.location.origin + '/dashboard.html'
      }
    });
    return { data, error };
  },

  async login(email, password) {
    if (!this.rateLimit('login', 5, 60000)) return { error: { message: 'Rate limit exceeded. Please wait.' } };

    let { data: authData, error: authErr } = await supabaseClient.auth.signInWithPassword({
      email: email,
      password: password
    });

    // Resolve dummy password legacy conflicts seamlessly
    if (authErr && authErr.message.toLowerCase().includes('invalid login credentials')) {
      const dummyPassword = "AsrPremium#2026";
      const { data: dummyData, error: dummyErr } = await supabaseClient.auth.signInWithPassword({
        email: email, password: dummyPassword
      });
      if (!dummyErr && dummyData.session) {
        await supabaseClient.auth.updateUser({ password: password });
        authData = dummyData;
        authErr = null;
      }
    }

    if (authErr) {
      return { error: authErr };
    }

    // Ensure local profile sync
    await supabaseClient.from('profiles').upsert({ email }, { onConflict: 'email' }).catch(() => { });

    return { error: null };
  },

  async signUp(email, password) {
    if (!this.rateLimit('signup', 5, 60000)) return { error: { message: 'Rate limit exceeded. Please wait.' } };

    const { data: signUpData, error: signUpErr } = await supabaseClient.auth.signUp({
      email: email,
      password: password
    });

    if (signUpErr) {
      if (signUpErr.message.toLowerCase().includes('already registered')) {
        return this.login(email, password);
      }
      return { error: signUpErr };
    }

    // Attempt to auto-create profile
    await supabaseClient.from('profiles').insert({ email, is_paid: false, credits: 0 }).catch(() => { });

    if (!signUpData.session) {
      return { error: null, verificationRequired: true };
    }

    return { error: null, verificationRequired: false };
  },

  async activatePayment(amount, credits) {
    const session = await this.getSession();
    if (!session) return false;

    const { error } = await supabaseClient
      .from('profiles')
      .update({ is_paid: true, credits: credits })
      .eq('email', session.email);

    return !error;
  },

  /* ---------- Backend API Methods ---------- */
  async createOrder(email, planName, amount, credits) {
    try {
      const res = await fetch(`${API_BASE_URL}/api/orders`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, plan_name: planName, amount, credits })
      });
      const data = await res.json();
      return data.success ? data.order : null;
    } catch (err) {
      console.error('Create order error:', err);
      return null;
    }
  },

  async verifyPayment(orderId, utr, email) {
    try {
      const res = await fetch(`${API_BASE_URL}/api/orders/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order_id: orderId, utr, email })
      });
      return await res.json();
    } catch (err) {
      console.error('Verify payment error:', err);
      throw err;
    }
  },


  /* ---------- CSV Export ---------- */
  exportCSV(headers, rows, filename = 'screening_results.csv') {
    const csvContent = [
      headers.join(','),
      ...rows.map(r => r.map(v => `"${v}"`).join(','))
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.setAttribute("href", url);
    link.setAttribute("download", filename);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  },

  /* ---------- Formatting ---------- */
  formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  },

  /* ---------- Guards ---------- */
  async requireLogin() {
    const loggedIn = await this.isLoggedIn();
    if (!loggedIn) {
      window.location.href = 'index.html';
      return false;
    }
    return true;
  },

  async requirePayment() {
    const loggedIn = await this.isLoggedIn();
    if (!loggedIn) {
      window.location.href = 'index.html';
      return false;
    }
    const paid = await this.isPaid();
    if (!paid) {
      window.location.href = 'payment.html';
      return false;
    }
    return true;
  },


  /* ---------- Database Screenings ---------- */
  async saveScreening(config, results) {
    const session = await this.getSession();
    if (!session) return null;

    const { data, error } = await supabaseClient
      .from('screenings')
      .insert({
        user_id: session.id,
        job_title: config.jobTitle || 'Unspecified Role',
        job_description: config.jdText,
        pass_threshold: config.passThreshold,
        total_analyzed: results.total,
        selected_count: results.selected.length,
        rejected_count: results.rejected.length
      })
      .select()
      .single();

    return { data, error };
  },

  async getScreenings() {
    const session = await this.getSession();
    if (!session) return [];

    const { data, error } = await supabaseClient
      .from('screenings')
      .select('*')
      .eq('user_id', session.id)
      .order('created_at', { ascending: false });

    return data || [];
  },

  /* ---------- Common UI Components ---------- */

  async renderNavbar(id) {
    const el = document.getElementById(id);
    if (!el) return;
    const session = await this.getSession();
    el.innerHTML = `
      <nav class="navbar animate-fadeInUp">
        <div class="navbar-brand" onclick="window.location.href='index.html'" style="cursor:pointer">
          <div class="navbar-brand-icon">📄</div>
          <span>ASR Services AI Screener</span>
        </div>
        <div class="navbar-right">
          ${session && session.email ? `
            <span class="navbar-email" style="font-size: 0.85rem; color: var(--text-muted); margin-right: 12px;">${session.email}</span>
            <a href="#" class="navbar-link" onclick="Utils.clearSession().then(() => window.location.href='index.html');">Logout</a>
          ` : `
            <a href="index.html#features" class="navbar-link">Features</a>
            <a href="index.html#login" class="btn btn-primary btn-sm" style="padding: 8px 20px;">Get Started</a>
          `}
        </div>
      </nav>
    `;
  },

  showModal(title, content) {
    let overlay = document.getElementById('modalOverlay');
    if (!overlay) {
      overlay = document.createElement('div');
      overlay.id = 'modalOverlay';
      overlay.className = 'modal-overlay';
      overlay.innerHTML = `
        <div class="modal">
          <div class="modal-header">
            <h3 id="modalTitle"></h3>
            <button class="modal-close" onclick="document.getElementById('modalOverlay').classList.remove('active')">×</button>
          </div>
          <div id="modalBody" style="font-size: 0.9rem; color: var(--text-secondary); line-height: 1.6; max-height: 70vh; overflow-y: auto;"></div>
        </div>
      `;
      document.body.appendChild(overlay);
    }
    document.getElementById('modalTitle').textContent = title;
    document.getElementById('modalBody').innerHTML = content;
    overlay.classList.add('active');
  },

};
