import QtQuick
import qs.Commons
import qs.Ui

Rectangle {
  id: root
  property string label: "Info"
  property string severity: "info"
  property color foreground: Color.foreground
  implicitWidth: badgeText.implicitWidth + Style.space(12)
  implicitHeight: badgeText.implicitHeight + Style.space(4)
  radius: Style.cornerRadius
  color: severity === "error" ? Qt.alpha(Color.urgent, 0.18)
    : severity === "warning" ? Qt.alpha(Color.urgent, 0.18)
    : Qt.alpha(Color.accent, 0.16)
  border.width: 1
  border.color: severity === "error" ? Qt.alpha(Color.urgent, 0.55)
    : severity === "warning" ? Qt.alpha(Color.urgent, 0.55)
    : Qt.alpha(Color.accent, 0.45)

  Text {
    id: badgeText
    anchors.centerIn: parent
    text: root.label
    color: root.foreground
    font.family: Style.font.family
    font.pixelSize: Style.font.caption
    elide: Text.ElideRight
  }
}
