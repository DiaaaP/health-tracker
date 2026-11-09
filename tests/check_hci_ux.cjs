const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const storage = new Map([['sana-data-version', 'sana-clean-2026-09-27']]);
const elements = new Map();
const documentEvents = {};
const document = {
  body: { classList: { toggle() {} } },
  activeElement: null,
  addEventListener: (name, callback) => { documentEvents[name] = callback; },
  querySelector(selector) {
    if (!elements.has(selector)) elements.set(selector, {
      hidden: true, textContent: '', value: '', dataset: {}, events: {},
      classList: { toggle() {}, remove() {} },
      addEventListener(name, callback) { this.events[name] = callback; },
      querySelectorAll: () => [],
      focus() { document.activeElement = this; }
    });
    return elements.get(selector);
  },
  querySelectorAll(selector) {
    return selector === '[data-go]' ? [this.querySelector('#summaryAddEntry')] : [];
  }
};
document.querySelector('#summaryAddEntry').dataset.go = 'log';
const context = vm.createContext({
  document, window: { scrollTo() {} }, setTimeout: fn => fn(),
  localStorage: {
    getItem: key => storage.get(key) ?? null,
    setItem: (key, value) => storage.set(key, String(value)),
    removeItem: key => storage.delete(key)
  }
});
const run = code => vm.runInContext(code, context);
const source = fs.readFileSync(path.join(__dirname, '../frontend/app.js'), 'utf8');
run(source.replace(/\binit\(\);\s*$/, ''));
run('bindEvents()');
const modal = elements.get('#clearDataModal');
const trigger = elements.get('#clearData');
const cancel = elements.get('#cancelClearData');
const confirm = elements.get('#confirmClearData');
storage.set('sana-logs', '[{"notes":"Keep me"}]');
storage.set('sana-periods', '[{"start_date":"2026-10-01"}]');
const before = JSON.stringify([...storage]);
let requests = 0;
context.testRequest = async () => { requests += 1; throw new Error('Offline'); };
run('apiRequest = testRequest');

async function main() {
  trigger.events.click();
  assert.equal(modal.hidden, false);
  assert.equal(document.activeElement, cancel);
  assert.equal(JSON.stringify([...storage]), before);
  assert.equal(requests, 0);
  cancel.events.click();
  assert.equal(modal.hidden, true);
  assert.equal(document.activeElement, trigger);
  assert.equal(JSON.stringify([...storage]), before);

  trigger.events.click();
  documentEvents.keydown({ key: 'Escape' });
  assert.equal(modal.hidden, true);
  assert.equal(JSON.stringify([...storage]), before);
  trigger.events.click();
  modal.events.click({ target: modal });
  assert.equal(modal.hidden, true);
  assert.equal(JSON.stringify([...storage]), before);

  trigger.events.click();
  confirm.focus();
  let prevented = false;
  modal.events.keydown({ key: 'Tab', shiftKey: false, preventDefault() { prevented = true; } });
  assert.equal(prevented, true);
  assert.equal(document.activeElement, cancel);

  // Keep the real clear-data action, replacing only network/render dependencies.
  run(`loadCalendarForecast = async () => {}; loadSummary = async () => {};
    renderForecastSummary = () => {}; renderCalendar = () => {};
    renderCharts = () => {}; updateSelectedDate = () => {}; showToast = () => {};`);
  await confirm.events.click();
  assert.equal(modal.hidden, true);
  assert.equal(requests, 1);
  assert.equal(storage.has('sana-logs'), false);
  assert.equal(storage.has('sana-periods'), false);
  assert.equal(storage.has('sana-data-version'), true);
  await confirm.events.click();
  assert.equal(requests, 1);

  run("state.lang = 'ru'; state.logs.clear(); state.periods = []; state.summary = null; renderServerSummary()");
  assert.equal(elements.get('#summaryStatus').textContent, 'Мало данных');
  assert.equal(elements.get('#summaryRange').textContent,
    'Не удалось синхронизировать данные. Сейчас показаны записи, сохранённые на этом устройстве.');
  assert.equal(run("t('apiSummary')"), 'Сводка данных');
  assert.equal(run("t('addEntry')"), 'Добавить запись');
  assert.equal(run("t('clearDataTitle')"), 'Очистить все данные?');
  elements.get('#summaryAddEntry').events.click();
  assert.equal(run('state.view'), 'log');
  assert.equal(run('state.logDate'), run('dateKey(today)'));
  console.log('HCI UX: cancel, Escape, backdrop, focus, confirmed deletion, empty state and diary CTA passed');
}
main().catch(error => { console.error(error); process.exitCode = 1; });
