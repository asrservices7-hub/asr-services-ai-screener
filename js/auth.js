/* ==============================
   Auth v3 — Simplified Email Login & Sign Up
   Works with or without Supabase
   ============================== */

document.addEventListener('DOMContentLoaded', async () => {
    // If already logged in, go to appropriate page
    const loggedIn = await Utils.isLoggedIn();
    if (loggedIn) {
        const paid = await Utils.isPaid();
        window.location.href = paid ? 'dashboard.html' : 'payment.html';
        return;
    }

    const form = document.getElementById('loginForm');
    const emailInput = document.getElementById('emailInput');
    const passwordInput = document.getElementById('passwordInput');
    const errorEl = document.getElementById('loginError');
    const submitBtn = document.getElementById('loginBtn');

    if (!form) return;

    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        errorEl.classList.remove('visible');

        const email = emailInput.value.trim().toLowerCase();
        const password = passwordInput.value;

        if (!email || !Utils.validateEmail(email)) {
            showError('Please enter a valid email address.');
            return;
        }

        if (!password || password.length < 6) {
            showError('Password must be at least 6 characters.');
            return;
        }

        submitBtn.disabled = true;
        const originalText = submitBtn.textContent;
        submitBtn.innerHTML = '<span class="spinner" style="width:20px;height:20px;border-width:2px;"></span> Please wait...';

        try {
            const mode = window._authMode || 'login';

            if (mode === 'signup') {
                const res = await Utils.signUp(email, password);
                if (res.error) {
                    showError(res.error.message || 'Sign up failed.');
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalText;
                    return;
                }
                if (res.verificationRequired) {
                    errorEl.style.color = 'var(--success)';
                    errorEl.textContent = '✅ Check your email to verify, then log in.';
                    errorEl.classList.add('visible');
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalText;
                    if (typeof switchAuthTab === 'function') switchAuthTab('login');
                    return;
                }
                // Success — go to dashboard (1 free credit)
                window.location.href = 'dashboard.html';
            } else {
                const res = await Utils.login(email, password);
                if (res.error) {
                    showError(res.error.message || 'Login failed.');
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalText;
                    return;
                }
                // Check credits
                const credits = await Utils.getCredits();
                window.location.href = credits > 0 ? 'dashboard.html' : 'payment.html';
            }
        } catch (err) {
            console.error(err);
            // Last resort: create local session
            await Utils.setLocalSession(email);
            window.location.href = 'dashboard.html';
        }
    });

    // Google Login
    const googleBtn = document.getElementById('googleLoginBtn');
    if (googleBtn) {
        googleBtn.addEventListener('click', async () => {
            try {
                const { error } = await Utils.signInWithGoogle();
                if (error) showError(error.message || 'Google login failed.');
            } catch (err) {
                showError('Could not initiate Google login.');
            }
        });
    }

    function showError(msg) {
        errorEl.style.color = 'var(--danger)';
        errorEl.textContent = msg;
        errorEl.classList.add('visible');
        emailInput.focus();
    }

    // Agree checkbox → enable button
    const agreeCheck = document.getElementById('agreeTerms');
    if (agreeCheck) {
        const updateBtn = () => {
            const emailOk = Utils.validateEmail(emailInput.value);
            const passOk = passwordInput.value.length >= 6;
            const agreeOk = agreeCheck.checked;
            submitBtn.disabled = !(emailOk && passOk && agreeOk);
        };
        agreeCheck.addEventListener('change', updateBtn);
        emailInput.addEventListener('input', () => {
            const emailOk = Utils.validateEmail(emailInput.value);
            if (emailInput.value && !emailOk) {
                errorEl.style.color = 'var(--danger)';
                errorEl.textContent = 'Valid email required.';
                errorEl.classList.add('visible');
            } else { errorEl.classList.remove('visible'); }
            updateBtn();
        });
        passwordInput.addEventListener('input', updateBtn);
    }
});
