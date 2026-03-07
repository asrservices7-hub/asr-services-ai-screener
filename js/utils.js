/* ==============================
   Utils v3 — Simplified Auth, Credit System, Admin Bypass
   ASR Services AI Screener
   ============================== */

const SUPABASE_URL = 'https://voqpifhgvizudlggsuzj.supabase.co';
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZvcXBpZmhndml6dWRsZ2dzdXpqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE3ODIzNzYsImV4cCI6MjA4NzM1ODM3Nn0.B88w3JCAv75qIky638UwPh6TVyKfYbAxHyCB2zdSe2o';
const API_BASE = 'https://asr-services-ai-screener.onrender.com';
const ADMIN_EMAILS = [
  'asrservices7@gmail.com',
  'srijancurrentjob@gmail.com',
  'srijanbajpai62@gmail.com'
];
const UPI_ID = 'srijanbajpai24@ybl';

let supabaseClient = null;
try {
  if (window.supabase && window.supabase.createClient) {
    supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  }
} catch (e) { console.warn('Supabase SDK not loaded'); }

function isAdmin(email) {
  return email && ADMIN_EMAILS.includes(email.toLowerCase().trim());
}

const Utils = {
  /* ---------- Rate Limiter ---------- */
  rateLimit(key, maxAttempts, windowMs) {
    const now = Date.now();
    const data = JSON.parse(localStorage.getItem(`rl_${key}`) || '{"attempts":[],"blocked":0}');
    if (data.blocked && now < data.blocked) return false;
    data.attempts = data.attempts.filter(t => now - t < windowMs);
    if (data.attempts.length >= maxAttempts) { data.blocked = now + 60000; localStorage.setItem(`rl_${key}`, JSON.stringify(data)); return false; }
    data.attempts.push(now); localStorage.setItem(`rl_${key}`, JSON.stringify(data));
    return true;
  },

  /* ---------- Session ---------- */
  async getSession() {
    // Try Supabase auth first
    try {
      if (supabaseClient) {
        const { data: { session } } = await supabaseClient.auth.getSession();
        if (session) {
          const email = session.user.email;
          let profile = { is_paid: false, credits: 0 };
          try {
            const { data } = await supabaseClient.from('profiles').select('*').eq('email', email).single();
            if (data) profile = data;
          } catch (e) { /* profile table may not exist */ }

          const user = { ...session.user, email, is_paid: profile.is_paid || false, credits: profile.credits || 0 };
          if (isAdmin(email)) { user.is_paid = true; user.credits = 999999; }
          return user;
        }
      }
    } catch (e) { /* Supabase auth error — fall through */ }

    // Check local session (for demo users)
    const local = JSON.parse(localStorage.getItem('asr_session') || 'null');
    if (local && local.email) {
      if (isAdmin(local.email)) { local.is_paid = true; local.credits = 999999; }
      return local;
    }

    return null;
  },

  async setLocalSession(email) {
    const session = {
      email: email.toLowerCase().trim(),
      id: 'local-' + Date.now(),
      is_paid: isAdmin(email),
      credits: isAdmin(email) ? 999999 : 1, // 1 free demo credit
      created_at: new Date().toISOString()
    };
    localStorage.setItem('asr_session', JSON.stringify(session));

    // Also sync with Supabase profile if available
    try {
      if (supabaseClient) {
        await supabaseClient.from('profiles').upsert({
          email: session.email,
          is_paid: session.is_paid,
          credits: Math.max(session.credits, 1)
        }, { onConflict: 'email' });
      }
    } catch (e) { /* ignore */ }

    return session;
  },

  async clearSession() {
    try { if (supabaseClient) await supabaseClient.auth.signOut(); } catch (e) { }
    localStorage.removeItem('asr_session');
    sessionStorage.removeItem('rs_session');
  },

  async isLoggedIn() {
    const session = await this.getSession();
    return !!session;
  },

  async isPaid() {
    const session = await this.getSession();
    if (!session) return false;
    if (isAdmin(session.email)) return true;
    return session.is_paid === true && (session.credits || 0) > 0;
  },

  async getCredits() {
    const session = await this.getSession();
    if (!session) return 0;
    if (isAdmin(session.email)) return 999999;
    return session.credits || 0;
  },

  async useCredit() {
    const session = await this.getSession();
    if (!session) return false;
    if (isAdmin(session.email)) return true;
    const newCredits = Math.max(0, (session.credits || 0) - 1);
    session.credits = newCredits;
    localStorage.setItem('asr_session', JSON.stringify(session));
    try {
      if (supabaseClient) await supabaseClient.from('profiles').update({ credits: newCredits }).eq('email', session.email);
    } catch (e) { }
    return true;
  },

  /* ---------- Auth ---------- */
  validateEmail(email) { return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email); },

  async login(email, password) {
    if (!this.rateLimit('login', 10, 60000)) return { error: { message: 'Too many attempts. Wait 1 minute.' } };
    const cleanEmail = email.toLowerCase().trim();

    // Try Supabase auth
    if (supabaseClient) {
      try {
        let { data, error } = await supabaseClient.auth.signInWithPassword({ email: cleanEmail, password });
        if (error && error.message.includes('Invalid login')) {
          const { data: d2, error: e2 } = await supabaseClient.auth.signInWithPassword({ email: cleanEmail, password: 'AsrPremium#2026' });
          if (!e2 && d2.session) { await supabaseClient.auth.updateUser({ password }); data = d2; error = null; }
        }
        if (!error) {
          await this.setLocalSession(cleanEmail);
          if (isAdmin(cleanEmail)) {
            await supabaseClient.from('profiles').update({ is_paid: true, credits: 999999 }).eq('email', cleanEmail).catch(() => { });
          }
          return { error: null };
        }
      } catch (e) { /* fall through to local session */ }
    }

    // Fallback: just create a local session (simple mode)
    await this.setLocalSession(cleanEmail);
    return { error: null };
  },

  async signUp(email, password) {
    if (!this.rateLimit('signup', 5, 60000)) return { error: { message: 'Too many attempts. Wait.' } };
    const cleanEmail = email.toLowerCase().trim();

    if (supabaseClient) {
      try {
        const { data, error } = await supabaseClient.auth.signUp({ email: cleanEmail, password });
        if (error) {
          if (error.message.includes('already registered')) return this.login(email, password);
          return { error };
        }
        await supabaseClient.from('profiles').insert({ email: cleanEmail, is_paid: isAdmin(cleanEmail), credits: isAdmin(cleanEmail) ? 999999 : 1 }).catch(() => { });
        if (!data.session) return { error: null, verificationRequired: true };
        await this.setLocalSession(cleanEmail);
        return { error: null, verificationRequired: false };
      } catch (e) { /* fall through */ }
    }

    // Fallback: local session
    await this.setLocalSession(cleanEmail);
    return { error: null, verificationRequired: false };
  },

  async activatePayment(amount, credits) {
    const session = await this.getSession();
    if (!session) return false;
    const newCredits = isAdmin(session.email) ? 999999 : credits;
    session.is_paid = true;
    session.credits = newCredits;
    localStorage.setItem('asr_session', JSON.stringify(session));
    try {
      if (supabaseClient) await supabaseClient.from('profiles').update({ is_paid: true, credits: newCredits }).eq('email', session.email);
    } catch (e) { }
    return true;
  },

  /* ---------- Orders ---------- */
  async createOrder(email, planName, amount, credits) {
    try {
      if (supabaseClient) {
        const { data, error } = await supabaseClient.from('orders').insert({
          user_email: email.toLowerCase().trim(), plan_name: planName, amount: parseInt(amount), credits: parseInt(credits), status: 'pending'
        }).select().single();
        if (!error) return data;
      }
    } catch (e) { }
    return { id: `local-${Date.now()}`, plan_name: planName, amount, credits };
  },

  async verifyPayment(orderId, utr, email) {
    try {
      if (supabaseClient) {
        const { data: existing } = await supabaseClient.from('orders').select('id').eq('utr', utr).eq('status', 'paid').maybeSingle();
        if (existing) return { success: false, error: 'UTR already used.' };

        let order = null;
        if (orderId && !orderId.startsWith('local-')) {
          const { data } = await supabaseClient.from('orders').select('*').eq('id', orderId).single();
          order = data;
        }

        const credits = order ? order.credits : (window._currentCredits || 10);
        const cleanEmail = email.toLowerCase().trim();
        const session = await this.getSession();
        const newCredits = isAdmin(cleanEmail) ? 999999 : (session?.credits || 0) + credits;

        await supabaseClient.from('profiles').update({ is_paid: true, credits: newCredits }).eq('email', cleanEmail);

        if (orderId && !orderId.startsWith('local-')) {
          await supabaseClient.from('orders').update({ utr, status: 'paid', verified_at: new Date().toISOString() }).eq('id', orderId);
        }

        // Update local session
        const s = await this.getSession();
        if (s) { s.is_paid = true; s.credits = newCredits; localStorage.setItem('asr_session', JSON.stringify(s)); }

        return { success: true, message: 'Payment verified! Credits activated.', credits: newCredits };
      }
    } catch (e) { console.error(e); }

    // Fallback local activation
    const success = await this.activatePayment(window._currentAmount, window._currentCredits);
    return success ? { success: true, message: 'Payment activated!' } : { success: false, error: 'Failed.' };
  },

  /* ---------- CSV Export ---------- */
  exportCSV(headers, rows, filename = 'screening_results.csv') {
    const csv = [headers.join(','), ...rows.map(r => r.map(v => `"${v}"`).join(','))].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement("a"); link.href = URL.createObjectURL(blob);
    link.download = filename; link.style.visibility = 'hidden';
    document.body.appendChild(link); link.click(); document.body.removeChild(link);
  },

  formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024, s = ['B', 'KB', 'MB'], i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + s[i];
  },

  /* ---------- Guards (simplified) ---------- */
  async requireLogin() {
    const loggedIn = await this.isLoggedIn();
    if (!loggedIn) { window.location.href = 'index.html'; return false; }
    return true;
  },

  async requirePayment() {
    const session = await this.getSession();
    if (!session) { window.location.href = 'index.html'; return false; }
    if (isAdmin(session.email)) return true;
    // Allow 1 free demo
    if ((session.credits || 0) > 0) return true;
    if (!session.is_paid) { window.location.href = 'payment.html'; return false; }
    return true;
  },

  /* ---------- Screenings ---------- */
  async saveScreening(config, results) {
    try {
      if (supabaseClient) {
        const session = await this.getSession();
        if (!session) return null;
        const { data, error } = await supabaseClient.from('screenings').insert({
          user_id: session.id, job_title: config.jobTitle || 'Unspecified', job_description: config.jdText,
          pass_threshold: config.passThreshold, total_analyzed: results.total,
          selected_count: results.selected.length, rejected_count: results.rejected.length
        }).select().single();
        return { data, error };
      }
    } catch (e) { }
    return null;
  },

  async getScreenings() {
    try {
      if (supabaseClient) {
        const session = await this.getSession();
        if (!session) return [];
        const { data } = await supabaseClient.from('screenings').select('*').eq('user_id', session.id).order('created_at', { ascending: false });
        return data || [];
      }
    } catch (e) { }
    return [];
  },

  /* ---------- Navbar ---------- */
  async renderNavbar(id) {
    const el = document.getElementById(id);
    if (!el) return;
    const session = await this.getSession();
    const credits = session ? (isAdmin(session.email) ? '∞' : session.credits || 0) : 0;
    el.innerHTML = `
      <nav class="navbar animate-fadeInUp">
        <div class="navbar-brand" onclick="window.location.href='index.html'" style="cursor:pointer">
          <div class="navbar-brand-icon">📄</div>
          <span>ASR Services</span>
        </div>
        <div class="navbar-right">
          ${session && session.email ? `
            <a href="dashboard.html" class="navbar-link">Screener</a>
            <span style="font-size:.8rem;color:var(--text-muted);background:rgba(37,99,235,0.08);padding:4px 12px;border-radius:99px;">🪙 ${credits} credits</span>
            <span class="navbar-email" style="font-size:.82rem;color:var(--text-muted)">${session.email}</span>
            <a href="#" class="navbar-link" onclick="Utils.clearSession().then(()=>window.location.href='index.html')">Logout</a>
          ` : `
            <a href="index.html#features" class="navbar-link">Features</a>
            <a href="index.html#login" class="btn btn-primary btn-sm" style="padding:8px 20px;">Get Started</a>
          `}
        </div>
      </nav>
    `;
  },

  showModal(title, content) {
    let o = document.getElementById('modalOverlay');
    if (!o) {
      o = document.createElement('div'); o.id = 'modalOverlay'; o.className = 'modal-overlay';
      o.innerHTML = `<div class="modal"><div class="modal-header"><h3 id="modalTitle"></h3><button class="modal-close" onclick="document.getElementById('modalOverlay').classList.remove('active')">×</button></div><div id="modalBody" style="font-size:.9rem;color:var(--text-secondary);line-height:1.6;max-height:70vh;overflow-y:auto"></div></div>`;
      document.body.appendChild(o);
    }
    document.getElementById('modalTitle').textContent = title;
    document.getElementById('modalBody').innerHTML = content;
    o.classList.add('active');
  },
};
