import QtQuick
import Quickshell
import Quickshell.Io
import "McpModel.js" as Model

QtObject {
  id: root

  property var owner: null
  property var data: ({ agents: [], stats: { agents: 0, servers: 0, issues: 0 }, diagnostics: [] })
  property bool loading: false
  property string statusMessage: "Starting local scan…"
  property bool statusWarning: false
  property int generation: 0
  property string pendingAction: ""
  property var pendingPlan: null
  property var pendingRequest: null
  property var comparison: null
  property var conversionPreview: null
  property var historyEntries: []
  property bool queuedRefresh: false
  readonly property string helperPath: decodeURIComponent(String(Qt.resolvedUrl("scripts/mcp-managerctl")).replace(/^file:\/\//, ""))

  function run(args, action, stdinPayload) {
    if (helper.running) {
      if (action === "scan") queuedRefresh = true
      else {
        statusWarning = true
        statusMessage = "Another MCP Manager operation is still running"
      }
      return false
    }
    pendingAction = action
    loading = true
    helper.stdinPayload = stdinPayload === undefined ? "" : String(stdinPayload)
    helper.command = [root.helperPath].concat(args)
    helper.running = true
    return true
  }

  function refresh() {
    generation += 1
    run(["scan"], "scan")
  }

  function recoverAndRefresh() {
    if (!run(["recover"], "recover")) return
  }

  function requestPlan(request) {
    pendingRequest = request
    if (!run(["plan-stdin"], "plan", JSON.stringify(request))) pendingRequest = null
  }

  function requestRestore(backupId, sourceId) {
    pendingRequest = {}
    if (!run(["restore", "--backup-id", String(backupId), "--source-id", String(sourceId)], "restore-plan"))
      pendingRequest = null
  }

  function loadHistory() { run(["history", "--limit", "30"], "history") }

  function forgetImport(sourceId) { run(["import-forget", "--source-id", String(sourceId)], "forget-import") }

  function applyPending() {
    if (!pendingPlan) return
    run(["apply-stdin", "--plan-id", String(pendingPlan.planId)], "apply", JSON.stringify(pendingRequest || {}))
  }

  function compare() { run(["compare"], "compare") }

  function convertPreview(sourceId, serverName, targetAdapter) {
    run(["convert-preview-stdin"], "convert", JSON.stringify({ sourceId: String(sourceId), serverName: String(serverName), targetAdapter: String(targetAdapter) }))
  }

  function registerImport(path, adapter, mode) {
    run(["import-register-stdin"], "import", JSON.stringify({ path: String(path), adapter: String(adapter), mode: String(mode) }))
  }

  function handle(action, value) {
    loading = false
    if (!value || value.ok !== true) {
      statusWarning = true
      statusMessage = value && value.error && value.error.message ? String(value.error.message) : "MCP helper failed"
      if (action === "plan" || action === "restore-plan") pendingPlan = null
      return
    }
    statusWarning = false
    if (action === "recover") {
      statusMessage = "Recovered local transaction state"
      Qt.callLater(root.refresh)
      return
    }
    if (action === "scan" || action === "doctor") {
      data = value.data || {}
      statusMessage = Model.summary(data)
      return
    }
    if (action === "history") {
      historyEntries = value.data && Array.isArray(value.data.entries) ? value.data.entries : []
      statusMessage = historyEntries.length + " redacted history entr" + (historyEntries.length === 1 ? "y" : "ies")
      return
    }
    if (action === "import" || action === "forget-import") {
      statusMessage = action === "import" ? "Import registered" : "Import forgotten"
      Qt.callLater(root.refresh)
      return
    }
    if (action === "compare") {
      comparison = value.data || null
      statusMessage = "Cross-agent comparison ready"
      return
    }
    if (action === "convert") {
      conversionPreview = value.data || null
      statusMessage = conversionPreview && conversionPreview.lossy ? "Conversion preview includes lossy fields" : "Conversion preview ready"
      return
    }
    if (action === "plan" || action === "restore-plan") {
      pendingPlan = value.data || null
      statusMessage = pendingPlan ? "Review the redacted preview before applying" : "No preview available"
      return
    }
    if (action === "apply") {
      pendingPlan = null
      pendingRequest = null
      statusMessage = "Saved and verified; refresh your agent if it was already open"
      Qt.callLater(root.loadHistory)
      Qt.callLater(root.refresh)
    }
  }

  property var helperProcess: Process {
    id: helper
    property string stdinPayload: ""
    stdinEnabled: true
    onStarted: {
      if (stdinPayload !== "") write(stdinPayload + "\n")
      stdinPayload = ""
    }
    stdout: StdioCollector { id: stdoutCollector; waitForEnd: true }
    stderr: StdioCollector { id: stderrCollector; waitForEnd: true }
    onExited: function(exitCode) {
      var output = String(stdoutCollector.text || "").trim()
      var value = Model.parseResponse(output)
      if (exitCode !== 0 && value.ok === true)
        value = { ok: false, error: { code: "helper-failed", message: "MCP helper failed" } }
      root.handle(root.pendingAction, value)
      if (root.queuedRefresh) {
        root.queuedRefresh = false
        Qt.callLater(root.refresh)
      }
    }
  }
}
