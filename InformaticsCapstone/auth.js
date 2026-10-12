// Talks to api/users.php (PHP + MySQL) instead of localStorage. All functions are async: use await.
async function request(url, options) {
  const res = await fetch(url, { credentials: 'same-origin', ...options });
  const data = res.status === 204 ? null : await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data?.error || `Request failed (HTTP ${res.status} from ${url})`);
  return data;
}

const post = (url, body) => request(url, {
  method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body)
});

function createUser(firstName, lastName, email, password) {
  return post('api/users.php?action=signup', { firstName, lastName, email, password });
}

function loginUser(email, password) {          // replaces findUser + setCurrentUser
  return post('api/users.php?action=login', { email, password });
}

function getCurrentUser() {                    // null when logged out
  return request('api/users.php?action=me').catch(() => null);
}

function logoutUser() {
  return request('api/users.php?action=logout', { method: 'POST' });
}
