import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import qs.Commons

ColumnLayout {
  id: root
  property var preview: null
  property color foreground: Color.foreground
  spacing: Style.space(5)
  Text { text: "REDACTED PREVIEW"; color: root.foreground; font.family: Style.font.family; font.pixelSize: Style.font.caption; font.bold: true }
  TextArea {
    Layout.fillWidth: true
    Layout.preferredHeight: Style.space(150)
    readOnly: true
    text: root.preview && Array.isArray(root.preview.textDiff) ? root.preview.textDiff.join("\n") : "No textual changes"
    color: root.foreground
    font.family: "monospace"
    font.pixelSize: Style.font.caption
    wrapMode: TextEdit.NoWrap
    background: Rectangle { color: Qt.alpha(root.foreground, 0.06); radius: Style.cornerRadius }
  }
  Repeater {
    model: root.preview && Array.isArray(root.preview.warnings) ? root.preview.warnings : []
    Text {
      required property string modelData
      Layout.fillWidth: true
      text: "• " + modelData
      color: Qt.alpha(root.foreground, 0.82)
      font.family: Style.font.family
      font.pixelSize: Style.font.caption
      wrapMode: Text.WordWrap
    }
  }
  Text { Layout.fillWidth: true; text: "Secret values are not included in this preview."; color: Qt.alpha(root.foreground, 0.7); font.family: Style.font.family; font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap }
}
