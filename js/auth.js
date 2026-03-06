/* ==============================
   Auth — Email Login & Sign Up with Supabase
   ============================== */

document.addEventListener('DOMContentLoaded', async () => {
    // If already logged in, redirect appropriately
    const loggedIn = await Utils.isLoggedIn();
    if (loggedIn) {
        const paid = await Utils.isPaid();
        if (paid) {
            window.location.href = 'dashboard.html';
        } else {
            window.location.href = 'payment.html';
        }
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

        // Hide previous errors
        errorEl.classList.remove('visible');

        const email = emailInput.value.trim().toLowerCase();
        const password = passwordInput.value;

        // Validate email
        if (!email) {
            showError('Please enter your email address.');
            return;
        }

        if (!Utils.validateEmail(email)) {
            showError('Please enter a valid email address.');
            return;
        }

        // Validate password
        if (!password || password.length < 6) {
            showError('Password must be at least 6 characters.');
            return;
        }

        // Show loading
        submitBtn.disabled = true;
        const originalText = submitBtn.textContent;
        submitBtn.innerHTML = '<span class="spinner" style="width:20px;height:20px;border-width:2px;"></span> Please wait...';

        try {
            const mode = window._authMode || 'login';

            if (mode === 'signup') {
                // Sign Up flow
                const res = await Utils.signUp(email, password);
                if (res.error) {
                    showError(res.error.message || 'Sign up failed. Please try again.');
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalText;
                    return;
                }

                if (res.verificationRequired) {
                    // Show success message for email verification
                    errorEl.style.color = 'var(--success)';
                    errorEl.textContent = '✅ Account created! Please check your email to verify, then log in.';
                    errorEl.classList.add('visible');
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalText;
                    // Auto-switch to login tab
                    if (typeof switchAuthTab === 'function') switchAuthTab('login');
                    return;
                }

                // If session was auto-created (no email verification required)
                window.location.href = 'payment.html';

            } else {
                // Login flow
                const res = await Utils.login(email, password);
                if (res.error) {
                    showError(res.error.message || 'Invalid login credentials.');
                    submitBtn.disabled = false;
                    submitBtn.textContent = originalText;
                    return;
                }

                // Check if paid → go to dashboard, else → go to payment
                const paid = await Utils.isPaid();
                if (paid) {
                    window.location.href = 'dashboard.html';
                } else {
                    window.location.href = 'payment.html';
                }
            }
        } catch (err) {
            console.error(err);
            showError('An unexpected error occurred: ' + (err.message || String(err)));
            submitBtn.disabled = false;
            submitBtn.textContent = originalText;
        }
    });

    // Google Login
    const googleBtn = document.getElementById('googleLoginBtn');
    if (googleBtn) {
        googleBtn.addEventListener('click', async () => {
            try {
                const { error } = await Utils.signInWithGoogle();
                if (error) {
                    showError(error.message || 'Google login failed.');
                }
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
            // Show/hide email validation error
            const emailOk = Utils.validateEmail(emailInput.value);
            if (emailInput.value && !emailOk) {
                errorEl.style.color = 'var(--danger)';
                errorEl.textContent = 'Valid professional email required.';
                errorEl.classList.add('visible');
            } else {
                errorEl.classList.remove('visible');
            }
            updateBtn();
        });
        passwordInput.addEventListener('input', updateBtn);
    }
});
