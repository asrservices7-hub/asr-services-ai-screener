-- ASR Services AI Screener — Database Schema Updates
-- Run this in Supabase SQL Editor

-- Orders Table
CREATE TABLE IF NOT EXISTS orders (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  user_email TEXT NOT NULL,
  plan_name TEXT NOT NULL,
  amount INTEGER NOT NULL,
  credits INTEGER NOT NULL,
  status TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'paid', 'failed', 'refunded')),
  utr TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW(),
  verified_at TIMESTAMPTZ
);

-- Payments Log Table
CREATE TABLE IF NOT EXISTS payments (
  id UUID DEFAULT gen_random_uuid() PRIMARY KEY,
  order_id UUID REFERENCES orders(id),
  user_email TEXT NOT NULL,
  amount INTEGER NOT NULL,
  utr TEXT NOT NULL,
  status TEXT DEFAULT 'verified' CHECK (status IN ('verified', 'pending', 'failed', 'refunded')),
  plan_name TEXT,
  credits_added INTEGER DEFAULT 0,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Index for fast lookups
CREATE INDEX IF NOT EXISTS idx_orders_user_email ON orders(user_email);
CREATE INDEX IF NOT EXISTS idx_orders_utr ON orders(utr);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_payments_user_email ON payments(user_email);

-- RLS Policies
ALTER TABLE orders ENABLE ROW LEVEL SECURITY;
ALTER TABLE payments ENABLE ROW LEVEL SECURITY;

-- Allow service role full access (backend uses service key)
CREATE POLICY "Service role full access on orders" ON orders FOR ALL USING (true) WITH CHECK (true);
CREATE POLICY "Service role full access on payments" ON payments FOR ALL USING (true) WITH CHECK (true);

-- Ensure profiles table has required columns (safe to run multiple times)
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='profiles' AND column_name='credits') THEN
    ALTER TABLE profiles ADD COLUMN credits INTEGER DEFAULT 0;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='profiles' AND column_name='is_paid') THEN
    ALTER TABLE profiles ADD COLUMN is_paid BOOLEAN DEFAULT false;
  END IF;
END $$;
