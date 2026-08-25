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
assert.strictEqual(model.clampedIndex(1, 3), 1);
assert.strictEqual(model.clampedIndex(9, 3), 2);
assert.strictEqual(model.clampedIndex(0, 0), -1);
assert.strictEqual(model.responsiveMode(false, 900, 700, 1), 'wide');
assert.strictEqual(model.responsiveMode(true, 900, 700, 1), 'compact');
assert.strictEqual(model.summary(data), '2 agents · 3 servers · 1 diagnostic');
assert.strictEqual(model.summary({ stats: { agents: 0, servers: 0, issues: 0 }, agents: [] }), '0 agents · 0 servers · 0 diagnostics');
assert.strictEqual(model.diagnosticCount({ agents: [{ sources: [{ diagnostics: [{ code: 'one' }] }], diagnostics: [{ code: 'one' }] }], diagnostics: [] }), 1);
assert.strictEqual(model.diagnosticCount({
  agents: [{ sources: [{ diagnostics: [{ code: 'active' }, { code: 'ignored', ignored: true }] }] }],
  diagnostics: [{ code: 'ignored-general', ignored: true }]
}), 1);
assert.deepStrictEqual(model.duplicatePayload({ name: 'alpha', enabled: true, command: 'echo', args: ['ok'] }), { name: 'alpha-copy', enabled: true, command: 'echo', args: ['ok'] });
assert.strictEqual(model.duplicatePayload({ name: 'alpha', command: 'echo', args: ['<secret hidden>'] }).args, undefined);
assert.deepStrictEqual(model.writableAgentIds([
  { id: 'codex', support: 'read-write', sources: [{ writable: true }] },
  { id: 'gemini', support: 'read-write', sources: [{ writable: true }] },
  { id: 'pi', support: 'read-only', sources: [{ writable: false }] }
], 'codex'), ['gemini']);
assert.strictEqual(model.agentNameById(data.agents, 'gemini'), 'Gemini CLI');
assert.strictEqual(model.agentNameById(data.agents, 'missing'), 'missing');
assert.deepStrictEqual(model.conversionPlanRequest({
  canApply: true,
  targetSourceId: 'src_target',
  payload: { name: 'alpha', command: 'echo' }
}), {
  sourceId: 'src_target',
  action: 'copy-server',
  serverName: 'alpha',
  payload: { name: 'alpha', command: 'echo' }
});
assert.strictEqual(model.conversionPlanRequest({ canApply: false, targetSourceId: 'src_target', payload: { name: 'alpha' } }), null);
const diagnosticEntries = model.diagnosticEntries(data);
assert.strictEqual(diagnosticEntries.length, 1);
assert.strictEqual(diagnosticEntries[0].serverName, 'beta');
assert.strictEqual(diagnosticEntries[0].severity, 'info');
assert.ok(model.diagnosticGuidance('relative-cwd').includes('absolute'));
data.agents[1].sources[0].servers[1].diagnostics[0].ignored = true;
assert.strictEqual(model.diagnosticEntries(data).length, 0);
data.stats.issues = 0;
assert.strictEqual(model.summary(data), '2 agents · 3 servers · 0 diagnostics');
data.stats.issues = 1;
delete data.agents[1].sources[0].servers[1].diagnostics[0].ignored;
assert.deepStrictEqual(model.historyForSource([{ sourceId: 's1', action: 'old' }, { sourceId: 's2' }, { sourceId: 's1', action: 'new' }], 's1').map(item => item.action), ['new', 'old']);
console.log('model tests passed');
