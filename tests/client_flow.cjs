// Run with Node.js: node tests/client_flow.cjs
// Exercise course-selection events and exam-mode transitions without a server.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const elements = new Map();
const classes = new Set();
const element = id => {
  if (!elements.has(id)) elements.set(id, { innerHTML: '', textContent: '', value: '', style: {}, dataset: {} });
  return elements.get(id);
};
const document = {
  body: { classList: {
    toggle(name, enabled) { enabled ? classes.add(name) : classes.delete(name); },
    remove(name) { classes.delete(name); }
  } },
  querySelector: element,
  querySelectorAll(selector) {
    const attribute = selector.match(/^\[data-(.+)\]$/)?.[1];
    if (!attribute) return [];
    const html = attribute === 'page' ? element('#app').innerHTML : element('#content').innerHTML;
    const matches = [...html.matchAll(new RegExp(`data-${attribute}="([^"]*)"`, 'g'))];
    return matches.map(match => element(`[data-${attribute}="${match[1]}"]`));
  }
};
// Attach dataset values just as the browser does for rendered buttons.
const queryAll = document.querySelectorAll;
document.querySelectorAll = selector => queryAll(selector).map(button => {
  for (const [key, value] of elements) {
    if (value === button) {
      const match = key.match(/^\[data-(.+)="(.*)"\]$/);
      if (match) button.dataset[match[1]] = match[2];
    }
  }
  return button;
});
const context = vm.createContext({
  document, window: { addEventListener() {} }, console,
  fetch: () => new Promise(() => {}), setInterval() {}, setTimeout() {}, confirm: () => true
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../app/client.js'), 'utf8'), context);
const fixture = {
  user: { id: 'candidate', name: 'Test Candidate', role: 'candidate' },
  courses: [{ id: 'CSC301', title: 'Database Systems' }, { id: 'CSC302', title: 'Networks' }],
  exams: [
    { id: 'database-paper', course: 'CSC301', title: 'Database theory', questions: ['q1'], duration: 30, status: 'scheduled' },
    { id: 'networks-paper', course: 'CSC302', title: 'Networks theory', questions: ['q2'], duration: 45, status: 'scheduled' }
  ],
  attempts: [], reviews: [], questions: [{ id: 'q1', text: 'Explain transactions.', maximum: 6 }]
};
vm.runInContext(`state=${JSON.stringify(fixture)};page='Examinations';examinations();`, context);
assert.match(element('#content').innerHTML, /Select a course to write/);
assert.doesNotMatch(element('#content').innerHTML, /data-start=/);

element('#exam-course').onchange({ target: { value: 'CSC301' } });
assert.match(element('#content').innerHTML, /Database theory/);
assert.doesNotMatch(element('#content').innerHTML, /Networks theory/);
assert.equal(classes.has('exam-mode'), false);

vm.runInContext(`
  var calls=[];
  api=async(action,data)=>{calls.push(action);return {id:'attempt-1',exam:'database-paper',answers:{q1:''},status:'active',revision:0,deadline:Date.now()/1000+1800};};
  refresh=async()=>{};
  page='Overview';overview();
`, context);

(async () => {
  await element('[data-start="database-paper"]').onclick();
  assert.equal(vm.runInContext('page', context), 'Examinations');
  assert.equal(vm.runInContext('calls.length', context), 0, 'Overview must not start the timer');
  assert.match(element('#content').innerHTML, /Database theory/);
  await element('[data-start="database-paper"]').onclick();
  assert.equal(vm.runInContext('calls[0]', context), 'start');
  assert.equal(classes.has('exam-mode'), true, 'An active attempt removes the decorative background');
  vm.runInContext("attempt=null;page='Results';draw();", context);
  assert.equal(classes.has('exam-mode'), false, 'Ordinary pages restore the background');
  console.log('Course selection, overview entry and exam background transitions passed.');
})().catch(error => { console.error(error); process.exitCode = 1; });
