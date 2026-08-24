import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui

Rectangle {
  id: root
  property var server: null
  property color foreground: Color.foreground
  Layout.fillWidth: true
  implicitHeight: details.implicitHeight + Style.space(16)
  color: Qt.alpha(root.foreground, 0.045)
  radius: Style.cornerRadius
  border.width: 1
  border.color: Qt.alpha(root.foreground, 0.16)

  function urlText() {
    if (!server || !server.url) return ""
    return typeof server.url === "object" ? String(server.url.display || "") : String(server.url)
  }

  ColumnLayout {
    id: details
    anchors.fill: parent
    anchors.margins: Style.space(8)
    spacing: Style.space(4)
    Text { text: root.server ? "SERVER DETAILS · " + String(root.server.name || "") : "SERVER DETAILS"; color: root.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; font.bold: true }
    Text { Layout.fillWidth: true; visible: !!(root.server && root.server.command); text: "Command: " + String(root.server ? root.server.command || "" : ""); color: Qt.alpha(root.foreground, 0.76); font.family: "monospace"; font.pixelSize: Style.font.caption; wrapMode: Text.WrapAnywhere }
    Text { Layout.fillWidth: true; visible: !!(root.server && root.server.args && root.server.args.length); text: "Arguments: " + String(root.server ? root.server.args.join(" ") : ""); color: Qt.alpha(root.foreground, 0.76); font.family: "monospace"; font.pixelSize: Style.font.caption; wrapMode: Text.WrapAnywhere }
    Text { Layout.fillWidth: true; visible: root.urlText() !== ""; text: "URL: " + root.urlText(); color: Qt.alpha(root.foreground, 0.76); font.family: "monospace"; font.pixelSize: Style.font.caption; wrapMode: Text.WrapAnywhere }
    Text { Layout.fillWidth: true; visible: !!(root.server && root.server.cwd); text: "Working directory: " + String(root.server ? root.server.cwd || "" : ""); color: Qt.alpha(root.foreground, 0.76); font.family: "monospace"; font.pixelSize: Style.font.caption; wrapMode: Text.WrapAnywhere }
    Text { Layout.fillWidth: true; visible: !!(root.server && root.server.environment && root.server.environment.length); text: "Environment names: " + (root.server ? root.server.environment.map(function(item) { return String(item.name || "") }).join(", ") : ""); color: Qt.alpha(root.foreground, 0.72); font.family: Style.font.family; font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap }
    Text { Layout.fillWidth: true; visible: !!(root.server && root.server.headers && root.server.headers.length); text: "Header names: " + (root.server ? root.server.headers.map(function(item) { return String(item.name || "") }).join(", ") : ""); color: Qt.alpha(root.foreground, 0.72); font.family: Style.font.family; font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap }
    Flow {
      Layout.fillWidth: true
      spacing: Style.space(4)
      Repeater {
        model: root.server && Array.isArray(root.server.diagnostics) ? root.server.diagnostics : []
        DiagnosticBadge {
          required property var modelData
          label: String(modelData.label || modelData.code || "Diagnostic")
          severity: String(modelData.severity || "info")
          foreground: root.foreground
        }
      }
    }
  }
}
