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
      count += (Array.isArray(source.diagnostics) ? source.diagnostics : []).filter(function(diagnostic) {
        return diagnostic && diagnostic.ignored !== true
      }).length
    })
  })
  return count + (data && Array.isArray(data.diagnostics) ? data.diagnostics : []).filter(function(diagnostic) {
    return diagnostic && diagnostic.ignored !== true
  }).length
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

function clampedIndex(index, length) {
  if (!(length > 0)) return -1
  return Math.max(0, Math.min(Number(index), length - 1))
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
  var agents = Number(stats.agents === undefined || stats.agents === null ? agentsFrom(data).length : stats.agents)
  var servers = Number(stats.servers === undefined || stats.servers === null ? serverCount(data) : stats.servers)
  var issues = Number(stats.issues === undefined || stats.issues === null ? diagnosticCount(data) : stats.issues)
  return agents + " agent" + (agents === 1 ? "" : "s") + " · " + servers + " server" + (servers === 1 ? "" : "s") + " · " + issues + " diagnostic" + (issues === 1 ? "" : "s")
}

function diagnosticGuidance(code) {
  var messages = {
    "url-credential": "Prefer an environment-variable reference instead of credentials or sensitive query data in the URL.",
    "literal-environment": "The value is hidden. Move credentials to an environment-variable reference when the agent supports it.",
    "relative-cwd": "Use an absolute working-directory path so behavior does not depend on where the agent starts.",
    "relative-command": "Use an absolute executable path or a command resolved directly through PATH.",
    "command-missing": "Install or correct the executable outside MCP Manager, then refresh this static scan.",
    "environment-missing": "Define the named environment variable before starting the agent.",
    "cross-agent-drift": "Use Compare to review how this server differs across agents.",
    "precedence-duplicate": "Review source precedence to confirm which definition the agent will use.",
    "malformed-config": "Repair the file's MCP syntax or schema before it can be managed.",
    "duplicate-server": "Remove or rename the duplicate definition.",
    "literal-secret": "Move the hidden credential to an environment-variable reference.",
    "invalid-url": "Use a complete http:// or https:// URL.",
    "unsupported-transport": "Use a transport supported by this agent adapter.",
    "unsafe-permissions": "Correct ownership or permissions outside MCP Manager before editing.",
    "cwd-missing": "Choose an existing working directory.",
    "sse-legacy": "Confirm the agent still requires the legacy SSE transport."
  }
  return messages[String(code || "")] || "Review this configuration finding before making changes."
}

function diagnosticEntries(data) {
  var entries = []
  function add(diag, agentName, sourceName, serverName) {
    if (!diag || diag.ignored === true) return
    entries.push({
      code: String(diag.code || "diagnostic"),
      diagnosticId: String(diag.diagnosticId || ""),
      label: String(diag.label || diag.code || "Diagnostic"),
      severity: String(diag.severity || "info"),
      agentName: String(agentName || "General"),
      sourceName: String(sourceName || ""),
      serverName: String(serverName || ""),
      guidance: diagnosticGuidance(diag.code)
    })
  }
  ;(data && Array.isArray(data.diagnostics) ? data.diagnostics : []).forEach(function(diag) {
    add(diag, "General", "", "")
  })
  agentsFrom(data).forEach(function(agent) {
    sourcesFrom(agent).forEach(function(source) {
      var serverCounts = {}
      ;(source.servers || []).forEach(function(server) {
        ;(server.diagnostics || []).forEach(function(diag) {
          var signature = String(diag.severity || "info") + "\u0000" + String(diag.code || "") + "\u0000" + String(diag.label || "")
          serverCounts[signature] = Number(serverCounts[signature] || 0) + 1
          add(diag, agent.name, source.pathDisplay, server.name)
        })
      })
      ;(source.diagnostics || []).forEach(function(diag) {
        var signature = String(diag.severity || "info") + "\u0000" + String(diag.code || "") + "\u0000" + String(diag.label || "")
        if (serverCounts[signature] > 0) {
          serverCounts[signature] -= 1
          return
        }
        add(diag, agent.name, source.pathDisplay, "")
      })
    })
  })
  var rank = { error: 0, warning: 1, info: 2 }
  entries.sort(function(a, b) {
    var severity = Number(rank[a.severity] === undefined ? 3 : rank[a.severity]) - Number(rank[b.severity] === undefined ? 3 : rank[b.severity])
    if (severity !== 0) return severity
    return (a.agentName + a.sourceName + a.serverName + a.label).localeCompare(b.agentName + b.sourceName + b.serverName + b.label)
  })
  return entries
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

function agentNameById(agents, id) {
  var wanted = String(id || "")
  var match = (Array.isArray(agents) ? agents : []).find(function(agent) {
    return agent && String(agent.id || "") === wanted
  })
  return match ? String(match.name || match.id || wanted) : wanted
}

function conversionPlanRequest(preview) {
  if (!preview || preview.canApply !== true || !preview.targetSourceId || !preview.payload) return null
  var name = String(preview.payload.name || "")
  if (!name) return null
  return {
    sourceId: String(preview.targetSourceId),
    action: "copy-server",
    serverName: name,
    payload: preview.payload
  }
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
    serverCount, wrapIndex, nextIndex, clampedIndex, responsiveMode, badgeForSource,
    badgeForAgent, diffLines, summary, diagnosticGuidance, diagnosticEntries, keyHelp, duplicatePayload,
    writableAgentIds, agentNameById, conversionPlanRequest, historyForSource
  }
}
