/* ==============================
   Utils — Supabase Integration, Session, CSV Export
   ASR Services v2.0
   ============================== */

// Supabase Configuration
const SUPABASE_URL = 'https://voqpifhgvizudlggsuzj.supabase.co';
const SUPABASE_ANON_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZvcXBpZmhndml6dWRsZ2dzdXpqIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NzE3ODIzNzYsImV4cCI6MjA4NzM1ODM3Nn0.B88w3JCAv75qIky638UwPh6TVyKfYbAxHyCB2zdSe2o';
const API_BASE = 'https://asr-services-ai-screener.onrender.com';
const ADMIN_EMAIL = 'asrservices7@gmail.com';

let supabaseClient = null;

// Initialize Supabase client if SDK is present
if (window.supabase && window.supabase.createClient) {
  supabaseClient = window.supabase.createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
}

function isAdmin(email) {
  return email && email.toLowerCase().trim() === ADMIN_EMAIL;
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
    try {
      if (!supabaseClient) return null;
      const { data: { session } } = await supabaseClient.auth.getSession();
      if (session) {
        const email = session.user.email;
        // Fetch profile
        const { data: profile } = await supabaseClient
          .from('profiles').select('*').eq('email', email).single();

        const userObj = {
          ...session.user,
          email: email,
          is_paid: profile?.is_paid || false,
          credits: profile?.credits || 0
        };

        // Admin always unlimited
        if (isAdmin(email)) {
          userObj.is_paid = true;
          userObj.credits = 999999;
        }

        return userObj;
      }
    } catch (e) {
      console.error('Session error:', e);
    }
    return null;
  },

  async setSession(data) {
    const existing = JSON.parse(sessionStorage.getItem('rs_session') || '{}');
    sessionStorage.setItem('rs_session', JSON.stringify({ ...existing, ...data }));
  },

  async clearSession() {
    try { await supabaseClient.auth.signOut(); } catch (e) { }
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
    return session.is_paid === true;
  },

  async getCredits() {
    const session = await this.getSession();
    if (!session) return 0;
    if (isAdmin(session.email)) return 999999;
    return session.credits || 0;
  },

  async hasCredits() {
    const credits = await this.getCredits();
    return credits > 0;
  },

  async useCredit() {
    const session = await this.getSession();
    if (!session) return false;
    if (isAdmin(session.email)) return true; // Never deduct from admin

    const newCredits = Math.max(0, (session.credits || 0) - 1);
    await supabaseClient.from('profiles')
      .update({ credits: newCredits })
      .eq('email', session.email);
    return true;
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

    // Ensure profile exists
    const cleanEmail = email.toLowerCase().trim();
    await supabaseClient.from('profiles').upsert({
      email: cleanEmail,
      is_paid: isAdmin(cleanEmail),
      credits: isAdmin(cleanEmail) ? 999999 : 0
    }, { onConflict: 'email' }).catch(() => { });

    // If admin, ensure unlimited
    if (isAdmin(cleanEmail)) {
      await supabaseClient.from('profiles')
        .update({ is_paid: true, credits: 999999 })
        .eq('email', cleanEmail).catch(() => { });
    }

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

    // Create profile
    const cleanEmail = email.toLowerCase().trim();
    await supabaseClient.from('profiles').insert({
      email: cleanEmail,
      is_paid: isAdmin(cleanEmail),
      credits: isAdmin(cleanEmail) ? 999999 : 0
    }).catch(() => { });

    if (!signUpData.session) {
      return { error: null, verificationRequired: true };
    }

    return { error: null, verificationRequired: false };
  },

  async activatePayment(amount, credits) {
    const session = await this.getSession();
    if (!session) return false;

    const newCredits = isAdmin(session.email) ? 999999 : credits;
    const { error } = await supabaseClient
      .from('profiles')
      .update({ is_paid: true, credits: newCredits })
      .eq('email', session.email);

    return !error;
  },

  /* ---------- Serverless API Methods (Direct Supabase) ---------- */
  async createOrder(email, planName, amount, credits) {
    try {
      const { data, error } = await supabaseClient
        .from('orders')
        .insert({
          user_email: email.toLowerCase().trim(),
          plan_name: planName,
          amount: parseInt(amount),
          credits: parseInt(credits),
          status: 'pending'
        })
        .select()
        .single();

      if (error) {
        console.error('Create order error:', error);
        return null;
      }
      return data;
    } catch (err) {
      console.error('Create order exception:', err);
      return null;
    }
  },

  async verifyPayment(orderId, utr, email) {
    try {
      // 1. Check if UTR already exists in paid orders
      const { data: existing } = await supabaseClient
        .from('orders')
        .select('id')
        .eq('utr', utr)
        .eq('status', 'paid')
        .maybeSingle();

      if (existing) {
        return { success: false, error: 'This UTR has already been used for another order.' };
      }

      // 2. Fetch order details
      let currentOrder = null;
      if (orderId) {
        const { data } = await supabaseClient.from('orders').select('*').eq('id', orderId).single();
        currentOrder = data;
      }

      // 3. Activate the profile
      const creditsToAdd = currentOrder ? currentOrder.credits : window._currentCredits;
      const amountPaid = currentOrder ? currentOrder.amount : window._currentAmount;
      const planName = currentOrder ? currentOrder.plan_name : 'Unknown Plan';
      const cleanEmail = email.toLowerCase().trim();

      const session = await this.getSession();
      if (!session) return { success: false, error: 'Not logged in' };

      const currentCredits = session.credits || 0;
      const newCredits = isAdmin(cleanEmail) ? 999999 : currentCredits + creditsToAdd;

      const { error: profileErr } = await supabaseClient
        .from('profiles')
        .update({ is_paid: true, credits: newCredits })
        .eq('email', cleanEmail);

      if (profileErr) return { success: false, error: 'Failed to update profile.' };

      // 4. Update order if it exists
      if (orderId) {
        await supabaseClient
          .from('orders')
          .update({ utr, status: 'paid', verified_at: new Date().toISOString() })
          .eq('id', orderId);

        await supabaseClient.from('payments').insert({
          order_id: orderId,
          user_email: cleanEmail,
          amount: amountPaid,
          utr,
          status: 'verified',
          plan_name: planName,
          credits_added: creditsToAdd
        }).catch(e => console.error(e));
      }

      return { success: true, message: 'Payment verified! Your credits have been activated.', credits: newCredits };
    } catch (err) {
      console.error('Verify payment error:', err);
      const success = await this.activatePayment(window._currentAmount, window._currentCredits);
      if (success) {
        return { success: true, message: 'Payment activated (Fallback mode)!' };
      }
      return { success: false, error: 'Verification failed.' };
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
    const session = await this.getSession();
    if (!session) {
      window.location.href = 'index.html';
      return false;
    }
    if (isAdmin(session.email)) return true;
    if (!session.is_paid) {
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
          <span>ASR Services</span>
        </div>
        <div class="navbar-right">
          ${session && session.email ? `
            <a href="agents.html" class="navbar-link">🤖 Agents</a>
            <span class="navbar-email" style="font-size: 0.85rem; color: var(--text-muted); margin-right: 12px;">${session.email}</span>
            <a href="#" class="navbar-link" onclick="Utils.clearSession().then(() => window.location.href='index.html');">Logout</a>
          ` : `
            <a href="index.html#features" class="navbar-link">Features</a>
            <a href="agents.html" class="navbar-link">🤖 Agents</a>
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
