import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import qs.Commons
import qs.Ui
import "McpModel.js" as Model
import "components"

Panel {
  id: root
  moduleName: "io.github.ef-code.mcp-manager"
  manageIpc: false

  property var anchorItem: null
  property var hostWidget: null
  property color foreground: bar ? bar.barForeground : Color.foreground
  property color surface: Color.popups.background
  property int selectedAgentIndex: 0
  property int selectedSourceIndex: 0
  property int selectedServerIndex: 0
  property string query: ""
  property string filter: "all"
  property bool helpOpen: false
  property bool editorOpen: false
  property bool importOpen: false
  property bool compareOpen: false
  property bool historyOpen: false
  property var editingServer: null
  property string pendingForgetSourceId: ""
  property string pendingAction: ""
  property string conversionTarget: "codex"
  property bool keyboardReturnPending: false

  property var backend: Controller { id: backendObject }
  readonly property var agents: Model.agentsFrom(backend.data)
  readonly property var selectedAgent: agents.length > 0 && selectedAgentIndex >= 0 && selectedAgentIndex < agents.length ? agents[selectedAgentIndex] : null
  readonly property var sources: Model.sourcesFrom(selectedAgent)
  readonly property var selectedSource: sources.length > 0 && selectedSourceIndex >= 0 && selectedSourceIndex < sources.length ? sources[selectedSourceIndex] : null
  readonly property var servers: Model.serversFrom(selectedSource, query, filter)
  readonly property var selectedServer: servers.length > 0 && selectedServerIndex >= 0 && selectedServerIndex < servers.length ? servers[selectedServerIndex] : null
  readonly property string mode: Model.responsiveMode(!!(bar && bar.vertical), panel.screenW, panel.screenH, Style.fontScale)
  readonly property var conversionTargets: Model.writableAgentIds(agents, selectedAgent ? String(selectedAgent.id) : "")
  readonly property string conversionTargetName: Model.agentNameById(agents, conversionTarget)

  function chooseUsefulSource() {
    if (sources.length === 0) return
    if (selectedSource && selectedSource.servers && selectedSource.servers.length > 0) return
    for (var i = 0; i < sources.length; i++) {
      if (sources[i].servers && sources[i].servers.length > 0) {
        selectedSourceIndex = i
        selectedServerIndex = 0
        return
      }
    }
  }

  onSourcesChanged: {
    if (selectedSourceIndex >= sources.length) selectedSourceIndex = Math.max(0, sources.length - 1)
    if (selectedSource && (!selectedSource.servers || selectedSource.servers.length === 0)) {
      for (var i = 0; i < sources.length; i++) {
        if (sources[i].servers && sources[i].servers.length > 0) {
          selectedSourceIndex = i
          break
        }
      }
    }
  }

  Connections {
    target: backend
    function onDataChanged() { Qt.callLater(root.chooseUsefulSource) }
  }

  function open() {
    root.controller.show()
  }

  function close() { root.controller.hide() }
  function toggle() { root.opened ? root.close() : root.open() }
  function closeForPopoutSwitch() {
    popoutSwitchClosing = true
    close()
    Qt.callLater(function() { popoutSwitchClosing = false })
  }
  function refresh() { backend.refresh() }

  function selectAgent(index) {
    if (agents.length === 0) return
    selectedAgentIndex = Model.wrapIndex(index, agents.length)
    selectedSourceIndex = 0
    selectedServerIndex = 0
  }

  function selectSource(index) {
    if (sources.length === 0) return
    selectedSourceIndex = Model.wrapIndex(index, sources.length)
    selectedServerIndex = 0
  }

  function selectServer(index) {
    selectedServerIndex = Model.clampedIndex(index, servers.length)
    keyCatcher.forceActiveFocus()
  }

  function moveCursor(dx, dy) {
    if (dx !== 0) {
      selectAgent(selectedAgentIndex + dx)
      return
    }
    if (sources.length > 0 && selectedServerIndex < 0) selectedServerIndex = 0
    if (servers.length > 0) selectedServerIndex = Model.nextIndex(selectedServerIndex, dy, servers.length)
    else if (sources.length > 0) selectedSourceIndex = Model.nextIndex(selectedSourceIndex, dy, sources.length)
  }

  function selectedRequest(action, payload) {
    if (!selectedSource || !selectedServer) return
    pendingAction = action
    backend.requestPlan({ sourceId: String(selectedSource.sourceId), action: action, serverName: String(selectedServer.name), payload: payload || {} })
  }

  function prepareToggle() {
    if (selectedServer && selectedSource && selectedSource.writable) selectedRequest("set-enabled", { enabled: !selectedServer.enabled })
    else backend.statusMessage = "This source is read-only"
  }

  function prepareRemove() {
    if (selectedServer && selectedSource && selectedSource.writable) selectedRequest("remove-server", {})
    else backend.statusMessage = "This source is read-only"
  }

  function prepareDuplicate() {
    if (!selectedServer || !selectedSource || !selectedSource.writable) {
      backend.statusMessage = "Choose a writable server before duplicating"
      return
    }
    var payload = Model.duplicatePayload(selectedServer)
    if (!payload) return
    pendingAction = "duplicate-server"
    backend.requestPlan({ sourceId: String(selectedSource.sourceId), action: "duplicate-server", serverName: String(selectedServer.name), payload: payload })
  }

  function prepareForgetImport() {
    if (!selectedSource || !selectedSource.imported) return
    pendingForgetSourceId = String(selectedSource.sourceId)
  }

  function cycleConversionTarget() {
    if (conversionTargets.length === 0) {
      backend.statusMessage = "No other writable target agent is available"
      return
    }
    var index = conversionTargets.indexOf(conversionTarget)
    conversionTarget = conversionTargets[Model.nextIndex(index < 0 ? 0 : index, 1, conversionTargets.length)]
  }

  function prepareAdd() {
    if (!selectedSource || !selectedSource.writable) {
      backend.statusMessage = "Choose a writable source before adding a server"
      return
    }
    editingServer = null
    editorOpen = true
    helpOpen = false
  }

  function prepareEdit() {
    if (!selectedServer || !selectedSource || !selectedSource.writable) {
      backend.statusMessage = "This server is read-only"
      return
    }
    editingServer = selectedServer
    editorOpen = true
    helpOpen = false
  }

  function editorSave(value) {
    editorOpen = false
    if (!selectedSource) return
    var action = editingServer ? "upsert-server" : "upsert-server"
    pendingAction = action
    backend.requestPlan({ sourceId: String(selectedSource.sourceId), action: action, serverName: editingServer ? String(editingServer.name) : String(value.name), payload: value })
  }

  function activate() {
    if (helpOpen) { helpOpen = false; return }
    if (backend.pendingPlan) return
    if (editorOpen) return
    if (selectedServer) prepareEdit()
    else prepareAdd()
  }

  function keyText(text) {
    var value = String(text || "").toLowerCase()
    if (value === "r") refresh()
    else if (value === "a") prepareAdd()
    else if (value === "e") prepareEdit()
    else if (value === "u") prepareDuplicate()
    else if (value === "s") prepareToggle()
    else if (value === "d" || value === "x") prepareRemove()
    else if (value === "i") importOpen = true
    else if (value === "c") { compareOpen = true; backend.compare() }
    else if (value === "o") backend.run(["doctor"], "doctor")
    else if (value === "y") { historyOpen = true; backend.loadHistory() }
    else if (value === "[") selectSource(selectedSourceIndex - 1)
    else if (value === "]") selectSource(selectedSourceIndex + 1)
    else if (value === "t") cycleConversionTarget()
    else if (value === "p" && selectedServer && selectedSource) backend.convertPreview(String(selectedSource.sourceId), String(selectedServer.name), conversionTarget)
    else if (value === "?" || value === "h") helpOpen = !helpOpen
    else if (value === "/") searchField.forceActiveFocus()
  }

  onOpenedChanged: {
    if (opened) {
      Qt.callLater(function() { keyCatcher.forceActiveFocus() })
      backend.recoverAndRefresh()
    } else {
      editorOpen = false
      importOpen = false
      compareOpen = false
      historyOpen = false
      helpOpen = false
      backend.pendingPlan = null
      pendingForgetSourceId = ""
    }
  }

  onConversionTargetsChanged: {
    if (conversionTargets.length > 0 && conversionTargets.indexOf(conversionTarget) < 0)
      conversionTarget = conversionTargets[0]
  }

  KeyboardPanel {
    id: panel
    anchorItem: root.anchorItem
    owner: root.hostWidget || root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: fittedContentWidth(Style.space(670))
    contentHeight: fittedContentHeight(contentColumn.implicitHeight, Style.space(690))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      blocked: searchField.activeFocus || editorOpen || importOpen || historyOpen || compareOpen || !!backend.conversionPreview || !!backend.pendingPlan || pendingForgetSourceId !== ""
      onMoveRequested: function(dx, dy) { root.moveCursor(dx, dy) }
      onReturnRequested: root.keyboardReturnPending = true
      onActivateRequested: {
        if (root.keyboardReturnPending) {
          root.keyboardReturnPending = false
          root.activate()
        } else {
          root.prepareToggle()
        }
      }
      onDeleteRequested: root.prepareRemove()
      onCloseRequested: root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(text) { root.keyText(text) }

      Flickable {
        id: panelFlick
        anchors.fill: parent
        contentWidth: width
        contentHeight: contentColumn.implicitHeight
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        flickableDirection: Flickable.VerticalFlick
        interactive: contentHeight > height
        ScrollBar.vertical: ScrollBar { policy: ScrollBar.AsNeeded }

        ColumnLayout {
          id: contentColumn
          width: panelFlick.width
          spacing: Style.space(10)

          RowLayout {
            Layout.fillWidth: true
            Text {
              text: "MCP MANAGER"
              color: root.foreground
              font.family: Style.font.family
              font.pixelSize: Style.font.title
              font.bold: true
            }
            Item { Layout.fillWidth: true }
            Text { text: Model.summary(backend.data); color: Qt.alpha(root.foreground, 0.72); font.family: Style.font.family; font.pixelSize: Style.font.caption }
            Button { text: "?"; focusable: true; onClicked: root.helpOpen = !root.helpOpen }
          }

          StatusBanner { Layout.fillWidth: true; message: backend.statusMessage; warning: backend.statusWarning; foreground: root.foreground }

          ConfirmSheet {
            visible: !!backend.pendingPlan
            preview: backend.pendingPlan ? backend.pendingPlan.preview : null
            title: root.pendingAction === "remove-server" ? "Remove server?" : root.pendingAction === "restore" ? "Restore this backup?" : "Apply MCP change?"
            foreground: root.foreground
            onCancelled: backend.pendingPlan = null
            onConfirmed: backend.applyPending()
          }
          ConfirmSheet {
            visible: root.pendingForgetSourceId !== ""
            preview: ({ textDiff: [], warnings: ["This removes only MCP Manager's import registration. The imported file is not changed."] })
            title: "Forget this import?"
            foreground: root.foreground
            onCancelled: root.pendingForgetSourceId = ""
            onConfirmed: {
              var sourceId = root.pendingForgetSourceId
              root.pendingForgetSourceId = ""
              backend.forgetImport(sourceId)
            }
          }

          ComparisonMatrix { visible: root.compareOpen; comparison: backend.comparison; foreground: root.foreground; onClosed: root.compareOpen = false }
          ConversionPreview { visible: !!backend.conversionPreview; preview: backend.conversionPreview; foreground: root.foreground; onClosed: backend.conversionPreview = null }
          HistorySheet {
            visible: root.historyOpen
            entries: backend.historyEntries
            sourceId: root.selectedSource ? String(root.selectedSource.sourceId) : ""
            foreground: root.foreground
            onClosed: root.historyOpen = false
            onRestoreRequested: function(backupId, sourceId) {
              root.historyOpen = false
              root.pendingAction = "restore"
              backend.requestRestore(backupId, sourceId)
            }
          }

          RowLayout {
            Layout.fillWidth: true
            TextField {
              id: searchField
              Layout.fillWidth: true
              placeholderText: "Search servers and diagnostics…"
              text: root.query
              onTextChanged: { root.query = text; root.selectedServerIndex = 0 }
              activeFocusOnTab: true
            }
            Button { text: root.filter === "all" ? "All" : root.filter; focusable: true; onClicked: root.filter = root.filter === "all" ? "enabled" : root.filter === "enabled" ? "issues" : root.filter === "issues" ? "disabled" : "all" }
          }

          Flow {
            id: globalTools
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(Style.space(38), childrenRect.height)
            Layout.minimumHeight: Style.space(38)
            spacing: Style.space(5)
            Button { text: "Import"; focusable: true; onClicked: root.importOpen = true }
            Button { text: "Compare"; focusable: true; onClicked: { root.compareOpen = true; backend.compare() } }
            Button { text: "Doctor"; focusable: true; onClicked: backend.run(["doctor"], "doctor") }
            Button { text: "History"; focusable: true; enabled: !!root.selectedSource; onClicked: { root.historyOpen = true; backend.loadHistory() } }
            Button { text: "Refresh"; focusable: true; onClicked: root.refresh() }
            Button { text: "Copy to: " + root.conversionTargetName; tooltipText: "Destination agent; click to choose the next available destination"; focusable: true; enabled: root.conversionTargets.length > 0; onClicked: root.cycleConversionTarget() }
            Button { text: "Preview copy"; focusable: true; enabled: !!root.selectedServer && !!root.selectedSource && root.conversionTargets.length > 0; onClicked: backend.convertPreview(String(root.selectedSource.sourceId), String(root.selectedServer.name), root.conversionTarget) }
          }

          SectionDivider { label: "AGENTS & SOURCES"; foreground: root.foreground }

          Loader {
            Layout.fillWidth: true
            active: root.helpOpen
            sourceComponent: Component {
              Rectangle {
                width: parent ? parent.width : 0
                implicitHeight: helpColumn.implicitHeight + Style.space(16)
                color: Qt.alpha(root.foreground, 0.06)
                radius: Style.cornerRadius
                ColumnLayout {
                  id: helpColumn
                  anchors.fill: parent
                  anchors.margins: Style.space(8)
                  Repeater {
                    model: Model.keyHelp()
                    RowLayout {
                      required property var modelData
                      Layout.fillWidth: true
                      Text { text: modelData.key; color: Color.accent; font.family: "monospace"; font.pixelSize: Style.font.caption; Layout.preferredWidth: Style.space(90) }
                      Text { text: modelData.label; color: root.foreground; font.family: Style.font.family; font.pixelSize: Style.font.caption }
                    }
                  }
                }
              }
            }
          }

          Loader {
            Layout.fillWidth: true
            sourceComponent: root.mode === "wide" ? wideNavigation : compactNavigation
          }

          Component {
            id: wideNavigation
            RowLayout {
              spacing: Style.space(10)
              AgentRail {
                Layout.preferredWidth: Style.space(180)
                Layout.minimumWidth: Style.space(150)
                Layout.maximumWidth: Style.space(190)
                Layout.alignment: Qt.AlignTop
                agents: root.agents
                selectedIndex: root.selectedAgentIndex
                foreground: root.foreground
                onSelected: function(index) { root.selectAgent(index) }
              }
              Rectangle {
                Layout.preferredWidth: 1
                Layout.fillHeight: true
                Layout.minimumHeight: Style.space(140)
                color: Qt.alpha(root.foreground, 0.16)
              }
              ColumnLayout {
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.alignment: Qt.AlignTop
                Text { text: root.selectedAgent ? String(root.selectedAgent.name) : "No configured agents"; color: root.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle; font.bold: true }
                Text { Layout.fillWidth: true; text: root.selectedAgent ? String(root.selectedAgent.notes || "") : "Discovery is allowlisted and local-only."; color: Qt.alpha(root.foreground, 0.7); font.family: Style.font.family; font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap }
                Text { visible: root.sources.length > 0; text: "SOURCE " + (root.selectedSourceIndex + 1) + " OF " + root.sources.length; color: Qt.alpha(root.foreground, 0.7); font.family: Style.font.family; font.pixelSize: Style.font.caption; font.bold: true }
                RowLayout {
                  Layout.fillWidth: true
                  visible: root.sources.length > 0
                  Button { text: "‹"; tooltipText: "Previous source ([)"; focusable: true; onClicked: root.selectSource(root.selectedSourceIndex - 1) }
                  SourceCard { Layout.fillWidth: true; Layout.minimumWidth: 0; Layout.maximumWidth: Style.space(420); source: root.selectedSource; selected: true; foreground: root.foreground; onChosen: root.selectSource(root.selectedSourceIndex) }
                  Button { text: "›"; tooltipText: "Next source (])"; focusable: true; onClicked: root.selectSource(root.selectedSourceIndex + 1) }
                }
                Text { visible: root.sources.length === 0; text: "No known source exists yet."; color: Qt.alpha(root.foreground, 0.7); font.family: Style.font.family; font.pixelSize: Style.font.caption }
              }
            }
          }

          Component {
            id: compactNavigation
            ColumnLayout {
              Layout.fillWidth: true
              Text { text: root.selectedAgent ? String(root.selectedAgent.name) : "No configured agents"; color: root.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle; font.bold: true }
              Flickable {
                Layout.fillWidth: true
                Layout.preferredHeight: Style.space(56)
                contentWidth: compactAgents.implicitWidth
                contentHeight: height
                clip: true
                flickableDirection: Flickable.HorizontalFlick
                boundsBehavior: Flickable.StopAtBounds
                Row {
                  id: compactAgents
                  spacing: Style.space(5)
                  Repeater {
                    model: root.agents
                    AgentCard {
                      required property var modelData
                      required property int index
                      width: Style.space(150)
                      height: Style.space(46)
                      agent: modelData
                      selected: index === root.selectedAgentIndex
                      foreground: root.foreground
                      onChosen: root.selectAgent(index)
                    }
                  }
                }
              }
              Text { visible: root.sources.length > 0; text: "SOURCE " + (root.selectedSourceIndex + 1) + " OF " + root.sources.length; color: Qt.alpha(root.foreground, 0.7); font.family: Style.font.family; font.pixelSize: Style.font.caption; font.bold: true }
              RowLayout {
                Layout.fillWidth: true
                visible: root.sources.length > 0
                Button { text: "‹"; tooltipText: "Previous source ([)"; focusable: true; onClicked: root.selectSource(root.selectedSourceIndex - 1) }
                SourceCard { Layout.fillWidth: true; Layout.minimumWidth: 0; source: root.selectedSource; selected: true; foreground: root.foreground; onChosen: root.selectSource(root.selectedSourceIndex) }
                Button { text: "›"; tooltipText: "Next source (])"; focusable: true; onClicked: root.selectSource(root.selectedSourceIndex + 1) }
              }
              Text { visible: root.sources.length === 0; text: "No known source exists yet."; color: Qt.alpha(root.foreground, 0.7); font.family: Style.font.family; font.pixelSize: Style.font.caption }
            }
          }

          RowLayout {
            Layout.fillWidth: true
            Text { text: root.selectedSource ? String(root.selectedSource.pathDisplay || "Source") : "Choose a source"; color: root.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; font.bold: true; elide: Text.ElideMiddle; Layout.fillWidth: true }
            DiagnosticBadge { label: root.selectedSource ? Model.badgeForSource(root.selectedSource) : "No source"; severity: root.selectedSource && root.selectedSource.status === "malformed" ? "error" : "info"; foreground: root.foreground }
          }

          SectionDivider { label: "MCP SERVERS"; foreground: root.foreground }

          Flow {
            id: sourceActions
            Layout.fillWidth: true
            Layout.preferredHeight: Math.max(Style.space(38), childrenRect.height)
            Layout.minimumHeight: Style.space(38)
            spacing: Style.space(5)
            Button { text: "Add"; focusable: true; enabled: !!(root.selectedSource && root.selectedSource.writable); onClicked: root.prepareAdd() }
            Button { text: "Edit"; focusable: true; enabled: !!(root.selectedServer && root.selectedSource && root.selectedSource.writable); onClicked: root.prepareEdit() }
            Button { text: "Duplicate"; focusable: true; enabled: !!(root.selectedServer && root.selectedSource && root.selectedSource.writable); onClicked: root.prepareDuplicate() }
            Button { text: root.selectedServer && root.selectedServer.enabled ? "Disable" : "Enable"; focusable: true; enabled: !!(root.selectedServer && root.selectedSource && root.selectedSource.writable); onClicked: root.prepareToggle() }
            Button { text: "Remove"; focusable: true; enabled: !!(root.selectedServer && root.selectedSource && root.selectedSource.writable); onClicked: root.prepareRemove() }
            Button { text: "Forget import"; focusable: true; visible: !!(root.selectedSource && root.selectedSource.imported); onClicked: root.prepareForgetImport() }
          }

          ColumnLayout {
            Layout.fillWidth: true
            visible: !root.editorOpen && !root.importOpen
            Repeater {
              model: root.servers
              ServerRow { required property var modelData; required property int index; server: modelData; selected: index === root.selectedServerIndex; foreground: root.foreground; onChosen: root.selectServer(index) }
            }
            EmptyState { visible: root.servers.length === 0; title: root.selectedSource ? "No servers in this source" : "No source selected"; description: root.selectedSource ? "Add a server when this source is writable, or import an explicit JSON, JSONC, or Codex TOML file." : "Select an agent and source to inspect its MCP definitions."; foreground: root.foreground }
          }

          SectionDivider { visible: !!root.selectedServer && !root.editorOpen && !root.importOpen; label: "SELECTED SERVER"; foreground: root.foreground }
          ServerDetails { visible: !!root.selectedServer && !root.editorOpen && !root.importOpen; server: root.selectedServer; foreground: root.foreground }

          ServerEditor { visible: root.editorOpen; server: root.editingServer; sourceId: root.selectedSource ? String(root.selectedSource.sourceId) : ""; foreground: root.foreground; onSaveRequested: root.editorSave(value); onCancelled: root.editorOpen = false }

          ImportSheet { visible: root.importOpen; foreground: root.foreground; onRegisterRequested: function(path, adapter, mode) { root.importOpen = false; backend.registerImport(path, adapter, mode) }; onCancelled: root.importOpen = false }

        }
      }
    }
  }
}
