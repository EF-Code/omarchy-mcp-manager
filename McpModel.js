function parseResponse(text) {
  try {
    var value = JSON.parse(String(text || ""))
    return value && typeof value === "object" ? value : { ok: false, error: { code: "invalid-response", message: "Helper returned no object" } }
  } catch (error) {
    return { ok: false, error: { code: "invalid-response", message: "Helper response was not JSON" } }
  }
}

function agentsFrom(data) {
  var agents = data && Array.isArray(data.agents) ? data.agents.slice() : []
  agents.sort(function(a, b) {
    var ad = a && a.isOmarchyDefault ? 0 : 1
    var bd = b && b.isOmarchyDefault ? 0 : 1
    if (ad !== bd) return ad - bd
    return String(a && a.name || "").localeCompare(String(b && b.name || ""))
  })
  return agents
}

function sourcesFrom(agent) {
  var sources = agent && Array.isArray(agent.sources) ? agent.sources.slice() : []
  sources.sort(function(a, b) {
    return Number(b && b.precedence || 0) - Number(a && a.precedence || 0)
  })
  return sources
}

function serversFrom(source, query, filter) {
  var servers = source && Array.isArray(source.servers) ? source.servers : []
  var needle = String(query || "").toLowerCase().trim()
  var wanted = String(filter || "all")
  return servers.filter(function(server) {
    if (!server) return false
    if (wanted === "enabled" && !server.enabled) return false
    if (wanted === "disabled" && server.enabled) return false
    if (wanted === "issues" && (!server.diagnostics || server.diagnostics.length === 0)) return false
    if (!needle) return true
    var haystack = [server.name, server.transport, server.command, server.cwd]
    ;(server.diagnostics || []).forEach(function(item) { haystack.push(item.label, item.code) })
    return haystack.join(" ").toLowerCase().indexOf(needle) !== -1
  })
}

function diagnosticCount(data) {
  var count = 0
  agentsFrom(data).forEach(function(agent) {
    sourcesFrom(agent).forEach(function(source) {
      count += Array.isArray(source.diagnostics) ? source.diagnostics.length : 0
    })
  })
  return count + (data && Array.isArray(data.diagnostics) ? data.diagnostics.length : 0)
}

function serverCount(data) {
  var count = 0
  agentsFrom(data).forEach(function(agent) {
    sourcesFrom(agent).forEach(function(source) { count += (source.servers || []).length })
  })
  return count
}

function wrapIndex(index, length) {
  if (!(length > 0)) return -1
  return ((Number(index) % length) + length) % length
}

function nextIndex(index, delta, length) {
  return wrapIndex(Number(index) + Number(delta), length)
}

function responsiveMode(vertical, width, height, scale) {
  if (vertical || Number(width) < 720 || Number(height) < 420) return "compact"
  if (Number(scale) >= 1.45) return "stacked"
  return "wide"
}

function badgeForSource(source) {
  if (!source) return "Unknown"
  if (source.status === "malformed") return "Malformed"
  if (source.status === "unsafe") return "Unsafe"
  if (source.status === "missing") return "Missing"
  if (source.managed) return "Managed"
  if (!source.writable) return "Read-only"
  if (source.imported) return "Imported"
  return "Ready"
}

function badgeForAgent(agent) {
  if (!agent) return ""
  if (agent.isOmarchyDefault) return "Default"
  if (agent.support === "read-write") return "Ready"
  return "Detected"
}

function diffLines(preview) {
  return preview && Array.isArray(preview.textDiff) ? preview.textDiff : []
}

function summary(data) {
  var stats = data && data.stats ? data.stats : {}
  var agents = Number(stats.agents || agentsFrom(data).length)
  var servers = Number(stats.servers || serverCount(data))
  var issues = Number(stats.issues || diagnosticCount(data))
  return agents + " agent" + (agents === 1 ? "" : "s") + " · " + servers + " server" + (servers === 1 ? "" : "s") + " · " + issues + " issue" + (issues === 1 ? "" : "s")
}

function keyHelp() {
  return [
    { key: "h / l", label: "previous / next agent" },
    { key: "[ / ]", label: "previous / next source" },
    { key: "j / k", label: "move through sources and servers" },
    { key: "/", label: "focus search" },
    { key: "a", label: "add server" },
    { key: "e", label: "edit selected" },
    { key: "u", label: "duplicate selected" },
    { key: "enter", label: "open editor / add server" },
    { key: "space", label: "prepare enable / disable" },
    { key: "s", label: "prepare enable / disable" },
    { key: "i / c / o", label: "import / compare / Doctor" },
    { key: "y", label: "redacted history" },
    { key: "t / p", label: "cycle target / copy preview" },
    { key: "r", label: "refresh" },
    { key: "esc", label: "close" }
  ]
}

function duplicatePayload(server) {
  if (!server) return null
  var payload = { name: String(server.name || "server") + "-copy", enabled: server.enabled !== false }
  if (server.command) {
    payload.command = String(server.command)
    var args = Array.isArray(server.args) ? server.args : []
    if (!args.some(function(item) { return String(item).indexOf("<secret hidden>") !== -1 })) payload.args = args.slice()
  }
  if (server.url && server.url.state === "clear" && server.url.display) {
    payload.url = String(server.url.display)
    payload.transport = String(server.transport || "http")
  }
  if (server.cwd) payload.cwd = String(server.cwd)
  return payload
}

function writableAgentIds(agents, currentId) {
  return (Array.isArray(agents) ? agents : []).filter(function(agent) {
    return agent && agent.id !== currentId && agent.support === "read-write" && (agent.sources || []).some(function(source) { return source && source.writable })
  }).map(function(agent) { return String(agent.id) })
}

function historyForSource(entries, sourceId) {
  return (Array.isArray(entries) ? entries : []).filter(function(entry) {
    return entry && String(entry.sourceId || "") === String(sourceId || "")
  }).reverse()
}

// Node consumes the same pure functions during repository tests; QML ignores
// this CommonJS bridge because `module` is not defined in its JS engine.
if (typeof module !== "undefined") {
  module.exports = {
    parseResponse, agentsFrom, sourcesFrom, serversFrom, diagnosticCount,
    serverCount, wrapIndex, nextIndex, responsiveMode, badgeForSource,
    badgeForAgent, diffLines, summary, keyHelp, duplicatePayload,
    writableAgentIds, historyForSource
  }
}
