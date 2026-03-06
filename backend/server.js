/* ==============================
   ASR Services AI Screener — Backend Server
   Express.js + Supabase
   ============================== */

require('dotenv').config();
const express = require('express');
const cors = require('cors');
const { createClient } = require('@supabase/supabase-js');

const app = express();
const PORT = process.env.PORT || 3001;

// --- Supabase Admin Client (service role) ---
let supabase = null;
if (process.env.SUPABASE_URL && process.env.SUPABASE_SERVICE_KEY) {
  supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_KEY);
} else {
  console.warn("⚠️  Supabase keys missing. Database features will be disabled.");
}

// --- Middleware ---
app.use(express.json());
app.use(cors({
  origin: [
    process.env.CORS_ORIGIN || 'https://asrservices24.netlify.app',
    'http://localhost:5500',
    'http://127.0.0.1:5500',
    'http://localhost:3000'
  ],
  credentials: true
}));

// --- Health Check ---
app.get('/api/health', (req, res) => {
  res.json({ status: 'ok', service: 'ASR Services AI Screener API', timestamp: new Date().toISOString() });
});

// --- Create Order ---
app.post('/api/orders', async (req, res) => {
  try {
    const { email, plan_name, amount, credits } = req.body;

    if (!email || !plan_name || !amount || !credits) {
      return res.status(400).json({ error: 'Missing required fields: email, plan_name, amount, credits' });
    }

    const { data, error } = await supabase
      .from('orders')
      .insert({
        user_email: email.toLowerCase().trim(),
        plan_name,
        amount: parseInt(amount),
        credits: parseInt(credits),
        status: 'pending'
      })
      .select()
      .single();

    if (error) {
      console.error('Order creation error:', error);
      return res.status(500).json({ error: 'Failed to create order' });
    }

    res.json({ success: true, order: data });
  } catch (err) {
    console.error('Server error:', err);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// --- Verify Payment (UTR Submission) ---
app.post('/api/orders/verify', async (req, res) => {
  try {
    const { order_id, utr, email } = req.body;

    if (!order_id || !utr || !email) {
      return res.status(400).json({ error: 'Missing required fields: order_id, utr, email' });
    }

    // Check if UTR is already used
    const { data: existingUTR } = await supabase
      .from('orders')
      .select('id')
      .eq('utr', utr)
      .eq('status', 'paid')
      .single();

    if (existingUTR) {
      return res.status(400).json({ error: 'This UTR has already been used for another order.' });
    }

    // Update order with UTR and mark as paid
    const { data: order, error: orderErr } = await supabase
      .from('orders')
      .update({
        utr,
        status: 'paid',
        verified_at: new Date().toISOString()
      })
      .eq('id', order_id)
      .eq('user_email', email.toLowerCase().trim())
      .select()
      .single();

    if (orderErr || !order) {
      console.error('Order verify error:', orderErr);
      return res.status(404).json({ error: 'Order not found or verification failed.' });
    }

    // Activate user profile: set is_paid = true and add credits
    const { data: profile } = await supabase
      .from('profiles')
      .select('credits')
      .eq('email', email.toLowerCase().trim())
      .single();

    const currentCredits = profile?.credits || 0;
    const newCredits = currentCredits + order.credits;

    const { error: profileErr } = await supabase
      .from('profiles')
      .update({ is_paid: true, credits: newCredits })
      .eq('email', email.toLowerCase().trim());

    if (profileErr) {
      console.error('Profile update error:', profileErr);
    }

    // Log the payment
    await supabase.from('payments').insert({
      order_id: order.id,
      user_email: email.toLowerCase().trim(),
      amount: order.amount,
      utr,
      status: 'verified',
      plan_name: order.plan_name,
      credits_added: order.credits
    }).catch(e => console.error('Payment log error:', e));

    res.json({
      success: true,
      message: 'Payment verified! Your credits have been activated.',
      credits: newCredits,
      order
    });
  } catch (err) {
    console.error('Server error:', err);
    res.status(500).json({ error: 'Internal server error' });
  }
});

// --- Get User Orders ---
app.get('/api/orders/:email', async (req, res) => {
  try {
    const email = req.params.email.toLowerCase().trim();

    const { data, error } = await supabase
      .from('orders')
      .select('*')
      .eq('user_email', email)
      .order('created_at', { ascending: false });

    if (error) {
      return res.status(500).json({ error: 'Failed to fetch orders' });
    }

    res.json({ orders: data || [] });
  } catch (err) {
    res.status(500).json({ error: 'Internal server error' });
  }
});

// --- Agent API Bridge (Bridge to Python Engines) ---
const { exec } = require('child_process');
const path = require('path');

const PROJECT_ROOT = path.resolve(__dirname, '..');

app.get('/api/agents/stats', (req, res) => {
  const cmd = `python3 asr_platform/asr_platform.py --dashboard --json`;
  exec(cmd, { cwd: PROJECT_ROOT }, (error, stdout, stderr) => {
    if (error) {
      console.error(`Exec error: ${error}`);
      return res.status(500).json({ error: 'Failed to Fetch Agent Stats' });
    }
    try {
      res.json(JSON.parse(stdout));
    } catch (e) {
      res.json({ output: stdout });
    }
  });
});

app.post('/api/agents/match', (req, res) => {
  const { query } = req.body;
  if (!query) return res.status(400).json({ error: 'Missing query' });

  const cmd = `python3 asr_platform/asr_platform.py --match "${query}" --json`;
  exec(cmd, { cwd: PROJECT_ROOT }, (error, stdout, stderr) => {
    if (error) {
      console.error(`Exec error: ${error}`);
      return res.status(500).json({ error: 'Matching Engine Failed' });
    }
    try {
      res.json(JSON.parse(stdout));
    } catch (e) {
      res.json({ output: stdout });
    }
  });
});

app.post('/api/agents/discover', (req, res) => {
  const cmd = `python3 asr_growth_engine/growth_engine.py --discover`;
  exec(cmd, { cwd: PROJECT_ROOT }, (error, stdout, stderr) => {
    if (error) {
      console.error(`Exec error: ${error}`);
      return res.status(500).json({ error: 'Discovery Engine Failed' });
    }
    res.json({ output: stdout, message: 'Discovery job started' });
  });
});

// --- Start Server ---
app.listen(PORT, () => {
  console.log(`🚀 ASR Services Backend running on port ${PORT}`);
  console.log(`   Health: http://localhost:${PORT}/api/health`);
});
