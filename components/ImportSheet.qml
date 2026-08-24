import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui

Rectangle {
  id: root
  property color foreground: Color.foreground
  signal registerRequested(string path, string adapter, string mode)
  signal cancelled()
  implicitHeight: content.implicitHeight + Style.space(18)
  Layout.fillWidth: true
  color: Qt.alpha(root.foreground, 0.06)
  radius: Style.cornerRadius
  border.width: 1
  border.color: Qt.alpha(Color.accent, 0.35)
  ColumnLayout {
    id: content
    anchors.fill: parent
    anchors.margins: Style.space(9)
    spacing: Style.space(7)
    Text { text: "IMPORT CONFIG"; color: root.foreground; font.family: Style.font.family; font.pixelSize: Style.font.body; font.bold: true }
    TextField { id: pathField; Layout.fillWidth: true; placeholderText: "Absolute JSON, JSONC, or Codex TOML path" }
    Text { Layout.fillWidth: true; text: "Read-only is the default. Manage in place authorizes only this exact file."; color: Qt.alpha(root.foreground, 0.7); font.family: Style.font.family; font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap }
    RowLayout {
      Layout.fillWidth: true
      Item { Layout.fillWidth: true }
      Button { text: "Cancel"; onClicked: root.cancelled() }
      Button { text: "Register read-only"; onClicked: root.registerRequested(String(pathField.text), "generic", "read") }
      Button { text: "Manage in place"; onClicked: root.registerRequested(String(pathField.text), "generic", "manage") }
    }
  }
}
