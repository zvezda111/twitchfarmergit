const form = document.getElementById("login-form");
const errEl = document.getElementById("l-err");
const totpRow = document.getElementById("totp-row");
const btn = document.getElementById("l-btn");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  errEl.textContent = "";
  btn.disabled = true;
  const body = {
    username: document.getElementById("l-user").value,
    password: document.getElementById("l-pass").value,
  };
  const totp = document.getElementById("l-totp").value.trim();
  if (totp) body.totp = totp;
  try {
    const res = await fetch("/api/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      window.location.href = "/";
      return;
    }
    if (data.totp_required) {
      totpRow.classList.remove("hidden");
      document.getElementById("l-totp").focus();
      errEl.textContent = "Введите код 2FA";
    } else {
      errEl.textContent = data.detail || ("Ошибка " + res.status);
    }
  } catch (err) {
    errEl.textContent = "Сеть недоступна";
  } finally {
    btn.disabled = false;
  }
});
