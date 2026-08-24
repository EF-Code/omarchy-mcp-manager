const assert = require('assert');
const model = require('../McpModel.js');

const data = {
  stats: { agents: 2, servers: 3, issues: 1 },
  agents: [
    { id: 'gemini', name: 'Gemini CLI', isOmarchyDefault: false, support: 'read-write', sources: [] },
    { id: 'codex', name: 'Codex', isOmarchyDefault: true, support: 'read-write', sources: [
      { sourceId: 's1', precedence: 100, status: 'ready', servers: [
        { name: 'alpha', enabled: true, transport: 'stdio', command: 'echo', diagnostics: [] },
        { name: 'beta', enabled: false, transport: 'http', diagnostics: [{ code: 'invalid-url', label: 'Malformed URL' }] }
      ] }
    ] }
  ]
};

assert.strictEqual(model.agentsFrom(data)[0].id, 'codex');
assert.strictEqual(model.badgeForAgent(model.agentsFrom(data)[0]), 'Default');
assert.strictEqual(model.serversFrom(data.agents[1].sources[0], 'alpha', 'enabled').length, 1);
assert.strictEqual(model.serversFrom(data.agents[1].sources[0], '', 'issues')[0].name, 'beta');
assert.strictEqual(model.wrapIndex(-1, 3), 2);
assert.strictEqual(model.nextIndex(2, 1, 3), 0);
assert.strictEqual(model.responsiveMode(false, 900, 700, 1), 'wide');
assert.strictEqual(model.responsiveMode(true, 900, 700, 1), 'compact');
assert.ok(model.summary(data).includes('2 agents'));
console.log('model tests passed');
