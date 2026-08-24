import QtQuick
import qs.Commons
import qs.Ui

Rectangle {
  id: root
  property string message: ""
  property bool warning: false
  property color foreground: Color.foreground
  visible: message !== ""
  implicitHeight: messageText.implicitHeight + Style.space(14)
  radius: Style.cornerRadius
  color: warning ? Qt.alpha(Color.urgent, 0.14) : Qt.alpha(Color.accent, 0.12)
  border.width: 1
  border.color: warning ? Qt.alpha(Color.urgent, 0.55) : Qt.alpha(Color.accent, 0.35)

  Text {
    id: messageText
    anchors.fill: parent
    anchors.margins: Style.space(7)
    text: root.message
    color: root.foreground
    font.family: Style.font.family
    font.pixelSize: Style.font.caption
    wrapMode: Text.WordWrap
    verticalAlignment: Text.AlignVCenter
  }
}
