window.login = async function () {
  const username = document.getElementById("username").value.trim();
  const password = document.getElementById("password").value;

  if (!username || !password) {
    alert("Username and password are required");
    return;
  }

  try {
    const res = await fetch("/auth/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include", // REQUIRED for cookie auth
      body: JSON.stringify({
        username: username,
        password: password
      })
    });

    const data = await res.json();

    if (!res.ok) {
      throw new Error(data.detail || "Invalid credentials");
    }

    // Role-based redirect
    if (data.role === "admin") {
      window.location.href = "/ui/admin/dashboard";
    } else if (data.role === "reseller") {
      window.location.href = "/ui/reseller/dashboard";
    } else {
      window.location.href = "/ui/user/dashboard";
    }

  } catch (err) {
    alert(err.message || "Login failed");
  }
};


window.logout = function () {
  /*
    Secure + HttpOnly cookies CANNOT be reliably removed from JS.
    Redirecting to server-side logout is the correct approach.
  */
  window.location.href = "/auth/logout";
};

