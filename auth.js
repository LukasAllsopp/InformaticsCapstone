const USERS_STORAGE_KEY = 'tripcastUsers';
const CURRENT_USER_STORAGE_KEY = 'currentUser';

function getUsers() {
  const storedUsers = localStorage.getItem(USERS_STORAGE_KEY);
  if (!storedUsers) return [];

  try {
    const users = JSON.parse(storedUsers);
    return Array.isArray(users) ? users : [];
  } catch (error) {
    console.error('Unable to read saved users.', error);
    return [];
  }
}

function saveUsers(users) {
  localStorage.setItem(USERS_STORAGE_KEY, JSON.stringify(users));
}

function findUser(lastName, password) {
  return getUsers().find(
    user => typeof user.lastName === 'string'
      && user.lastName.toLowerCase() === lastName.trim().toLowerCase()
      && user.password === password
  );
}

function createUser(firstName, lastName, password, email = '') {
  const users = getUsers();
  const normalizedLastName = lastName.trim().toLowerCase();

  if (users.some(user => typeof user.lastName === 'string'
    && user.lastName.toLowerCase() === normalizedLastName)) {
    throw new Error('An account with that last name already exists.');
  }

  const user = {
    firstName: firstName.trim(),
    lastName: lastName.trim(),
    password,
    email: email.trim(),
    locations: [],
    tripStartDate: null,
    tripEndDate: null,
    
    
  };

  users.push(user);
  saveUsers(users);
  return user;
}

function setCurrentUser(user) {
  localStorage.setItem(CURRENT_USER_STORAGE_KEY, JSON.stringify(user));
}
