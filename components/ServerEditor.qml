import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui

Rectangle {
  id: root
  property var server: null
  property string sourceId: ""
  property color foreground: Color.foreground
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
    TextField { id: nameField; Layout.fillWidth: true; placeholderText: "Server name"; text: root.server ? String(root.server.name || "") : "" }
    TextField { id: commandField; Layout.fillWidth: true; placeholderText: "Command (stdio)"; text: root.server ? String(root.server.command || "") : "" }
    TextField { id: urlField; Layout.fillWidth: true; placeholderText: root.server && root.server.url && root.server.url.state === "set" ? "URL hidden — leave blank to preserve" : "URL (optional HTTP/SSE)"; text: root.server && root.server.url && root.server.url.state !== "set" && root.server.url.display ? String(root.server.url.display) : "" }
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
          if (String(commandField.text).trim() !== "") { value.command = String(commandField.text).trim(); value.args = [] }
          if (String(urlField.text).trim() !== "") { value.url = String(urlField.text).trim(); value.transport = "http" }
          root.saveRequested(value)
        }
      }
    }
  }
}
