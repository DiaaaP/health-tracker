/* Pure date/mode logic shared by the calendar and its offline fallback. */
const SanaTracking = (() => {
  const DAY = 86400000;
  function parse(key) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(key || '')) return null;
    const date = new Date(key + 'T00:00:00Z');
    return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === key ? date : null;
  }
  function difference(first, last) { return Math.round((parse(last) - parse(first)) / DAY); }
  function add(key, days) { return new Date(parse(key).getTime() + days * DAY).toISOString().slice(0, 10); }
  function normalize(value) {
    const valid = value && typeof value === 'object';
    return {
      mode: valid && value.mode === 'pregnancy' && parse(value.last_period_date) ? 'pregnancy' : 'cycle',
      last_period_date: valid && parse(value.last_period_date) ? value.last_period_date : null,
      cycle_resume_date: valid && parse(value.cycle_resume_date) ? value.cycle_resume_date : null
    };
  }
  function pregnancy(lmp, key) {
    const elapsed = difference(lmp, key);
    return { last_period_date: lmp, due_date: add(lmp, 280), elapsed_days: elapsed,
      weeks: Math.floor(Math.max(0, elapsed) / 7), days: Math.max(0, elapsed) % 7,
      trimester: elapsed < 98 ? 1 : elapsed < 196 ? 2 : 3 };
  }
  function calendar(result, settings, year, month, today) {
    const tracking = normalize(settings);
    result.tracking_mode = tracking.mode;
    result.cycle_resume_date = tracking.cycle_resume_date;
    result.pregnancy = null; result.pregnancy_dates = [];
    if (tracking.mode === 'pregnancy') {
      const details = pregnancy(tracking.last_period_date, today);
      Object.assign(result, { has_data: false, cycle_length: null, period_length: null,
        current_cycle_day: null, current_phase: 'pregnancy', next_period_start: null,
        expected_period_start: null, next_fertile_start: null, next_fertile_end: null,
        late_days: 0, is_late: false, predicted_period_dates: [], fertile_dates: [], ovulation_dates: [], pregnancy: details });
      const last = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
      for (let day = 1; day <= last; day++) {
        const key = year + '-' + String(month + 1).padStart(2, '0') + '-' + String(day).padStart(2, '0');
        if (key >= tracking.last_period_date && key <= details.due_date) result.pregnancy_dates.push(key);
      }
    }
    return result;
  }
  return { parse, difference, add, normalize, pregnancy, calendar };
})();
if (typeof module !== 'undefined') module.exports = SanaTracking;
