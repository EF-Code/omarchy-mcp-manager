import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui

Rectangle {
  id: root
  property var preview: null
  property color foreground: Color.foreground
  signal closed()
  Layout.fillWidth: true
  implicitHeight: body.implicitHeight + Style.space(16)
  color: Qt.alpha(root.preview && root.preview.lossy ? Color.urgent : Color.accent, 0.10)
  radius: Style.cornerRadius
  border.width: 1
  border.color: Qt.alpha(root.preview && root.preview.lossy ? Color.urgent : Color.accent, 0.45)
  ColumnLayout {
    id: body
    anchors.fill: parent
    anchors.margins: Style.space(8)
    spacing: Style.space(5)
    RowLayout {
      Layout.fillWidth: true
      Text { text: "CONVERSION PREVIEW"; color: root.foreground; font.family: Style.font.family; font.pixelSize: Style.font.caption; font.bold: true }
      Item { Layout.fillWidth: true }
      Button { text: "Close"; onClicked: root.closed() }
    }
    Text {
      Layout.fillWidth: true
      text: root.preview ? String(root.preview.targetName || "Target") + " · " + (root.preview.lossy ? "lossy warnings" : "representable") : ""
      color: root.foreground
      font.family: Style.font.family
      font.pixelSize: Style.font.body
    }
    Text {
      Layout.fillWidth: true
      text: root.preview && root.preview.payload ? JSON.stringify(root.preview.payload, null, 2) : ""
      color: Qt.alpha(root.foreground, 0.78)
      font.family: "monospace"
      font.pixelSize: Style.font.caption
      wrapMode: Text.Wrap
    }
    Repeater {
      model: root.preview && Array.isArray(root.preview.warnings) ? root.preview.warnings : []
      Text {
        required property string modelData
        Layout.fillWidth: true
        text: "• " + modelData
        color: Color.urgent
        font.family: Style.font.family
        font.pixelSize: Style.font.caption
        wrapMode: Text.WordWrap
      }
    }
    Text {
      Layout.fillWidth: true
      text: "No embedded secret values are copied."
      color: Qt.alpha(root.foreground, 0.7)
      font.family: Style.font.family
      font.pixelSize: Style.font.caption
    }
  }
}
