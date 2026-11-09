const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const source = fs.readFileSync(path.join(__dirname, '../frontend/app.js'), 'utf8');
const storage = new Map([['sana-data-version', 'sana-clean-2026-09-27']]);
const elements = new Map();
const context = vm.createContext({
  localStorage: {
    getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: key => storage.delete(key)
  },
  document: {
    querySelector: selector => {
      if (!elements.has(selector)) elements.set(selector, { textContent: '', innerHTML: '' });
      return elements.get(selector);
    },
    querySelectorAll: () => []
  },
  window: { scrollTo() {} }
});
// Load application functions without starting network requests or event handlers.
vm.runInContext(source.replace(/\binit\(\);\s*$/, ''), context);

for (const [lang, guest, greeting] of [['ru', 'Гость', 'Здравствуйте'], ['kk', 'Қонақ', 'Сәлем']]) {
  vm.runInContext(`state.lang = '${lang}'; state.authToken = '';`, context);
  storage.set('sana-user-name', 'Старое имя');
  vm.runInContext('updateAuthUI()', context);
  assert.equal(elements.get('#pageTitle').textContent, greeting);
  assert.equal(elements.get('#profileName').textContent, guest);
  assert.equal(elements.get('#sideProfileName').textContent, guest);
  assert.match(elements.get('.avatar').innerHTML, /#icon-user/);

  storage.set('sana-user-name', 'Дана');
  vm.runInContext("state.authToken = 'test-session'; updateAuthUI()", context);
  assert.equal(elements.get('#pageTitle').textContent, greeting + ', Дана');
  assert.equal(elements.get('#profileName').textContent, 'Дана');
  assert.equal(elements.get('.avatar').textContent, 'Д');

  // Logging out must clear visible identity even if a stored name remains.
  vm.runInContext("state.authToken = ''; updateAuthUI()", context);
  assert.equal(elements.get('#pageTitle').textContent, greeting);
  assert.equal(elements.get('#sideProfileName').textContent, guest);
}
console.log('Profile identity: guest, login, logout and both languages passed');
