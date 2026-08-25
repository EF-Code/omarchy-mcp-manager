import QtQuick
import QtQuick.Layouts
import qs.Commons

RowLayout {
  id: root
  property string label: ""
  property color foreground: Color.foreground
  Layout.fillWidth: true
  Layout.topMargin: Style.space(5)
  Layout.bottomMargin: Style.space(2)
  spacing: Style.space(8)

  Rectangle {
    Layout.fillWidth: true
    Layout.preferredHeight: 1
    color: Qt.alpha(root.foreground, 0.16)
  }

  Text {
    visible: root.label !== ""
    text: root.label
    color: Qt.alpha(root.foreground, 0.62)
    font.family: Style.font.family
    font.pixelSize: Style.font.caption
    font.bold: true
    font.letterSpacing: 0.7
  }

  Rectangle {
    Layout.fillWidth: true
    Layout.preferredHeight: 1
    color: Qt.alpha(root.foreground, 0.16)
  }
}
