import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui

ColumnLayout {
  id: root
  property string label: "Secret"
  property string state: "set"
  property color foreground: Color.foreground
  spacing: Style.space(2)
  Text { text: root.label; color: root.foreground; font.family: Style.font.family; font.pixelSize: Style.font.caption }
  Text {
    text: root.state === "environment-reference" ? "Environment reference (value hidden)" : root.state === "set" ? "Set (value hidden)" : "Not set"
    color: Qt.alpha(root.foreground, 0.72)
    font.family: Style.font.family
    font.pixelSize: Style.font.caption
  }
}
