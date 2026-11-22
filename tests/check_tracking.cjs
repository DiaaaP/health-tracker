const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const tracking = require('../frontend/tracking.js');

assert.equal(tracking.parse('2026-02-30'), null);
assert.equal(tracking.parse('2024-02-29').toISOString().slice(0, 10), '2024-02-29');
assert.equal(tracking.difference('2026-08-30', '2026-11-22'), 84);
assert.deepEqual(tracking.pregnancy('2026-08-30', '2026-11-22'), {
  last_period_date: '2026-08-30', due_date: '2027-06-06', elapsed_days: 84, weeks: 12, days: 0, trimester: 1
});

const source = fs.readFileSync(path.join(__dirname, '../frontend/app.js'), 'utf8');
const storage = new Map([['sana-data-version', 'sana-clean-2026-09-27']]);
const nodes = new Map();
const node = selector => {
  if (!nodes.has(selector)) nodes.set(selector, {
    value: '', hidden: true, textContent: '', checked: false, disabled: false,
    classList: { add() {}, remove() {}, toggle() {} }, addEventListener() {},
    setAttribute() {}, focus() {}, querySelectorAll: () => []
  });
  return nodes.get(selector);
};
const context = vm.createContext({SanaTracking: tracking,
  localStorage: {getItem:k => storage.get(k) ?? null, setItem:(k,v) => storage.set(k,String(v)), removeItem:k => storage.delete(k)},
  document: {querySelector:node, querySelectorAll:() => [], addEventListener() {}, body:{classList:{toggle(){}}}},
  window: {}, MutationObserver: class {observe() {}}, setTimeout:fn=>fn()
});
const run = code => vm.runInContext(code, context);
run(source.replace(/\binit\(\);\s*/, ''));
run(`renderForecastSummary = () => {}; updateSelectedDate = () => {}; renderCalendar = () => {};
  renderCharts = () => {}; loadSummary = async () => {}; loadCalendarForecast = async () => {};
  apiRequest = async () => { throw new Error('Offline'); };`);

async function main() {
  // Viewing/calculating cannot enable a mode. Activation needs explicit confirmation.
  const lmp = run('SanaTracking.add(dateKey(today), -84)');
  node('#pregnancyLastPeriod').value = lmp;
  await run('activatePregnancyMode()');
  assert.equal(run('state.tracking.mode'), 'cycle');
  assert.equal(storage.has('sana-tracking:guest'), false);
  node('#pregnancyConfirmed').checked = true;
  await run('activatePregnancyMode()');
  assert.equal(run('state.tracking.mode'), 'pregnancy');
  assert.equal(JSON.parse(storage.get('sana-tracking:guest')).pending, true);
  assert.equal(run('readTrackingCache().mode'), 'pregnancy');

  // A guest's pregnancy must not leak into an account or another account's cache.
  storage.set('sana-user-id', '1');
  run("state.authToken = 'first'; state.tracking = readTrackingCache()");
  assert.equal(run('state.tracking.mode'), 'cycle');
  await assert.rejects(run("persistTracking({mode:'pregnancy',last_period_date:'2026-08-30'})"));
  assert.equal(run('state.tracking.mode'), 'cycle');
  storage.set('sana-user-id', '2');
  assert.equal(run('readTrackingCache().mode'), 'cycle');
  run("state.authToken = ''; state.tracking = readTrackingCache()");
  assert.equal(run('state.tracking.mode'), 'pregnancy');

  // All three mutation entry points block the request, including stale/open forms.
  let requests = 0;
  context.recordRequest = async () => {requests++;};
  run('apiRequest = recordRequest; showToast = () => {}');
  await run('savePeriodDetails({preventDefault(){}})');
  await run('deleteEditedPeriod()');
  assert.equal(requests, 0);

  run('apiRequest = async () => { throw new Error("Offline"); }');
  await run('finishPregnancyMode()');
  assert.equal(run('state.tracking.mode'), 'cycle');
  assert.equal(run('state.tracking.cycle_resume_date'), run('dateKey(today)'));

  // The offline calculation must also exclude the pregnancy gap from prediction.
  run(`state.periods = [{id:1, start_date:SanaTracking.add(dateKey(today),-84),end_date:null}];
    state.calendar = buildLocalCalendarForecast(today.getFullYear(), today.getMonth())`);
  assert.equal(run('state.calendar.has_data'), false);
  assert.equal(run('state.calendar.is_late'), false);
  run(`state.periods.push({id:2,start_date:dateKey(today),end_date:null});
    state.calendar = buildLocalCalendarForecast(today.getFullYear(), today.getMonth())`);
  assert.equal(run('state.calendar.current_cycle_day'), 1);
  assert.equal(run('state.calendar.next_period_start'), run('SanaTracking.add(dateKey(today),28)'));
  console.log('Tracking: explicit activation, offline persistence, account isolation, period guards and cycle restart passed');
}
main().catch(error=>{console.error(error); process.exitCode=1;});
