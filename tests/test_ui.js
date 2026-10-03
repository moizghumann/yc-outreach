// Exercise the actual inline application script with controllable network responses.
// Uses only Node's built-in modules; no browser or external test dependency.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const html = fs.readFileSync(path.join(__dirname, '..', 'index.html'), 'utf8');
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1];

function company(id) {
  return {id, name: id, source: 'test', slug: id, screen: {
    state: 'research', lane: 'vertical_operations', checked_at: '2026-10-03',
    reasons: [], holds: [], unknowns: []
  }};
}

function harness() {
  const elements = new Map(), pending = [];
  function element(id) {
    if (!elements.has(id)) elements.set(id, {
      value: '', textContent: '', innerHTML: '', disabled: false, hidden: false,
      classList: {toggle() {}}, scrollIntoView() {}
    });
    return elements.get(id);
  }
  const context = vm.createContext({
    document: {getElementById: element},
    localStorage: {getItem() {return null;}, setItem() {}},
    navigator: {clipboard: {writeText: async () => {}}},
    URL, URLSearchParams,
    fetch(url) {
      if (url === '/api/evaluate') return new Promise((resolve, reject) => {
        pending.push({
          succeed(result) {resolve({ok: true, json: async () => result});},
          fail(message) {reject(new Error(message));}
        });
      });
      return Promise.resolve({ok: true, json: async () => []});
    }
  });
  vm.runInContext(script, context);
  function save(c, text) {
    const card = context.blankCard(c);
    card.draft = {subject: c.name, body: text};
    element('card').value = JSON.stringify(card);
    return element('saveCard').onclick();
  }
  return {element, pending, show: context.show, save};
}

test('delayed success cannot put A outreach in B panel', async () => {
  const h = harness(), a = company('a'), b = company('b');
  h.show(a);
  const saving = h.save(a, 'A outreach');
  h.show(b);
  const before = h.element('evaluation').textContent;
  h.pending[0].succeed({draft_ready: true});
  await saving;
  assert.equal(h.element('detailTitle').textContent, 'b');
  assert.equal(h.element('evaluation').textContent, before);
  assert.equal(h.element('draft').textContent, 'No reviewed draft yet.');
  assert.equal(h.element('cardStatus').textContent, '');
  assert.equal(h.element('copyDraft').disabled, true);
});

test('delayed error cannot overwrite B status or copy state', async () => {
  const h = harness(), a = company('a'), b = company('b');
  h.show(a);
  const saving = h.save(a, 'A outreach');
  h.show(b);
  h.element('cardStatus').textContent = 'B status';
  h.element('copyDraft').disabled = false;
  h.pending[0].fail('A failed');
  await saving;
  assert.equal(h.element('cardStatus').textContent, 'B status');
  assert.equal(h.element('copyDraft').disabled, false);
});

test('switching away and back still discards the old A response', async () => {
  const h = harness(), a = company('a');
  h.show(a);
  const saving = h.save(a, 'Old A outreach');
  h.show(company('b'));
  h.show(a);
  h.pending[0].succeed({draft_ready: true});
  await saving;
  assert.equal(h.element('draft').textContent, 'No reviewed draft yet.');
  assert.equal(h.element('copyDraft').disabled, true);
});

test('closing the panel discards an outstanding response', async () => {
  const h = harness(), a = company('a');
  h.show(a);
  const saving = h.save(a, 'A outreach');
  h.element('close').onclick();
  h.pending[0].succeed({draft_ready: true});
  await saving;
  assert.equal(h.element('detail').hidden, true);
  assert.equal(h.element('copyDraft').disabled, true);
  assert.equal(h.element('cardStatus').textContent, '');
});

for (const oldOutcome of ['success', 'error']) {
  test(`an older same-company ${oldOutcome} cannot replace a newer evaluation`, async () => {
    const h = harness(), a = company('a');
    h.show(a);
    const oldSave = h.save(a, 'Old outreach');
    const newSave = h.save(a, 'New outreach');
    h.pending[1].succeed({draft_ready: true, revision: 'new'});
    await newSave;
    if (oldOutcome === 'success') h.pending[0].succeed({draft_ready: false, revision: 'old'});
    else h.pending[0].fail('Old failure');
    await oldSave;
    assert.equal(JSON.parse(h.element('evaluation').textContent).revision, 'new');
    assert.equal(h.element('draft').textContent, 'a\n\nNew outreach');
    assert.equal(h.element('copyDraft').disabled, false);
    assert.equal(h.element('cardStatus').textContent, 'Saved and evaluated. Nothing sent.');
  });
}

test('the current evaluation still updates the panel and unlocks its draft', async () => {
  const h = harness(), a = company('a');
  h.show(a);
  const saving = h.save(a, 'Current outreach');
  assert.equal(h.element('copyDraft').disabled, true);
  h.pending[0].succeed({draft_ready: true});
  await saving;
  assert.equal(h.element('draft').textContent, 'a\n\nCurrent outreach');
  assert.equal(h.element('copyDraft').disabled, false);
});
