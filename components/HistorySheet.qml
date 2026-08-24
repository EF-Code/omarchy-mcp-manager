import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui
import "../McpModel.js" as Model

Rectangle {
  id: root
  property var entries: []
  property string sourceId: ""
  property color foreground: Color.foreground
  readonly property var visibleEntries: Model.historyForSource(entries, sourceId)
  signal closed()
  signal restoreRequested(string backupId, string sourceId)
  Layout.fillWidth: true
  implicitHeight: content.implicitHeight + Style.space(18)
  color: Qt.alpha(root.foreground, 0.06)
  radius: Style.cornerRadius
  border.width: 1
  border.color: Qt.alpha(Color.accent, 0.35)

  ColumnLayout {
    id: content
    anchors.fill: parent
    anchors.margins: Style.space(9)
    spacing: Style.space(6)
    RowLayout {
      Layout.fillWidth: true
      Text { text: "REDACTED HISTORY"; color: root.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; font.bold: true }
      Item { Layout.fillWidth: true }
      Button { text: "Close"; onClicked: root.closed() }
    }
    Text { visible: root.visibleEntries.length === 0; text: "No verified mutations for this source."; color: Qt.alpha(root.foreground, 0.7); font.family: Style.font.family; font.pixelSize: Style.font.caption }
    Repeater {
      model: root.visibleEntries
      RowLayout {
        required property var modelData
        Layout.fillWidth: true
        Text { Layout.fillWidth: true; text: String(modelData.action || "change") + (modelData.serverName ? " · " + String(modelData.serverName) : "") + " · " + String(modelData.status || "recorded"); color: root.foreground; font.family: Style.font.family; font.pixelSize: Style.font.caption; elide: Text.ElideRight }
        Button { text: modelData.backupAvailable === false ? "Backup expired" : "Restore preview"; enabled: !!modelData.backupId && modelData.backupAvailable !== false; onClicked: root.restoreRequested(String(modelData.backupId || ""), String(modelData.sourceId || "")) }
      }
    }
  }
}
