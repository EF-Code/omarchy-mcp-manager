import QtQuick
import QtQuick.Controls as QQC
import QtQuick.Layouts
import qs.Commons
import qs.Ui

Rectangle {
  id: root
  property var server: null
  property string sourceId: ""
  property color foreground: Color.foreground
  property string transportMode: root.server && ["http", "sse"].indexOf(String(root.server.transport || "")) !== -1 ? "http" : "stdio"
  signal saveRequested(var value)
  signal cancelled()
  Layout.fillWidth: true
  implicitHeight: form.implicitHeight + Style.space(18)
  color: Qt.alpha(root.foreground, 0.06)
  radius: Style.cornerRadius
  border.width: 1
  border.color: Qt.alpha(Color.accent, 0.35)

  ColumnLayout {
    id: form
    anchors.fill: parent
    anchors.margins: Style.space(9)
    spacing: Style.space(7)
    Text { text: root.server ? "EDIT SERVER" : "ADD SERVER"; color: root.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; font.bold: true }
    RowLayout {
      Layout.fillWidth: true
      Text { text: "Transport"; color: Qt.alpha(root.foreground, 0.75); font.family: Style.font.family; font.pixelSize: Style.font.caption }
      Button { text: (root.transportMode === "stdio" ? "✓ " : "") + "Local command"; enabled: !root.server; onClicked: root.transportMode = "stdio" }
      Button { text: (root.transportMode === "http" ? "✓ " : "") + "HTTP"; enabled: !root.server; onClicked: root.transportMode = "http" }
      Item { Layout.fillWidth: true }
    }
    TextField { id: nameField; Layout.fillWidth: true; placeholderText: "Server name"; text: root.server ? String(root.server.name || "") : "" }
    TextField { id: commandField; visible: root.transportMode === "stdio"; Layout.fillWidth: true; placeholderText: "Command (stdio)"; text: root.server ? String(root.server.command || "") : "" }
    QQC.TextArea {
      id: argsField
      visible: root.transportMode === "stdio"
      Layout.fillWidth: true
      Layout.preferredHeight: Style.space(72)
      placeholderText: "Arguments — one per line"
      text: root.server && root.server.args ? root.server.args.join("\n") : ""
      wrapMode: TextEdit.NoWrap
      color: root.foreground
      font.family: "monospace"
      font.pixelSize: Style.font.caption
      background: Rectangle {
        color: Qt.alpha(root.foreground, 0.045)
        border.width: 1
        border.color: Qt.alpha(root.foreground, 0.18)
        radius: Style.cornerRadius
      }
    }
    TextField { id: cwdField; visible: root.transportMode === "stdio"; Layout.fillWidth: true; placeholderText: "Working directory (optional)"; text: root.server ? String(root.server.cwd || "") : "" }
    TextField { id: urlField; visible: root.transportMode === "http"; Layout.fillWidth: true; placeholderText: root.server && root.server.url && root.server.url.state === "set" ? "URL hidden — leave blank to preserve" : "HTTP URL"; text: root.server && root.server.url && root.server.url.state !== "set" && root.server.url.display ? String(root.server.url.display) : "" }
    Text { Layout.fillWidth: true; text: "Existing secret and environment values remain hidden and are never copied automatically."; color: Qt.alpha(root.foreground, 0.7); font.family: Style.font.family; font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap }
    RowLayout {
      Layout.fillWidth: true
      Item { Layout.fillWidth: true }
      Button { text: "Cancel"; focusable: true; onClicked: root.cancelled() }
      Button {
        text: "Preview"
        focusable: true
        onClicked: {
          var value = { name: String(nameField.text).trim() }
          var command = String(commandField.text).trim()
          var argsText = String(argsField.text)
          var oldArgsText = root.server && root.server.args ? root.server.args.join("\n") : ""
          var args = argsText === "" ? [] : argsText.split("\n")
          var cwd = String(cwdField.text).trim()
          var url = String(urlField.text).trim()
          if (root.transportMode === "stdio" && command !== "" && (!root.server || command !== String(root.server.command || "") || argsText !== oldArgsText)) {
            value.command = command
            value.args = args
          }
          if (root.transportMode === "stdio" && cwd !== "" && (!root.server || cwd !== String(root.server.cwd || ""))) value.cwd = cwd
          if (root.transportMode === "http" && url !== "" && (!root.server || !root.server.url || url !== String(root.server.url.display || ""))) {
            value.url = url
            value.transport = "http"
          }
          root.saveRequested(value)
        }
      }
    }
  }
}
