import QtQuick
import QtQuick.Layouts
import qs.Commons

ColumnLayout {
  id: root
  property string title: "Nothing here"
  property string description: ""
  property color foreground: Color.foreground
  Layout.fillWidth: true
  Layout.fillHeight: true
  spacing: Style.space(8)
  Text { text: root.title; color: root.foreground; font.family: Style.font.family; font.pixelSize: Style.font.subtitle; font.bold: true }
  Text { Layout.fillWidth: true; text: root.description; color: Qt.alpha(root.foreground, 0.7); font.family: Style.font.family; font.pixelSize: Style.font.caption; wrapMode: Text.WordWrap }
}
