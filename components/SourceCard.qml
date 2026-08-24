import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui

Button {
  id: root
  property var source: null
  property bool selected: false
  property color foreground: Color.foreground
  signal chosen()
  Layout.fillWidth: true
  Layout.preferredHeight: Style.space(62)
  hasCursor: selected
  activeFocusOnTab: true
  onClicked: root.chosen()

  contentItem: ColumnLayout {
    spacing: Style.space(2)
    Text {
      Layout.fillWidth: true
      text: root.source ? String(root.source.pathDisplay || "Source") : "Source"
      color: root.foreground
      font.family: Style.font.family
      font.pixelSize: Style.font.caption
      elide: Text.ElideMiddle
    }
    Text {
      Layout.fillWidth: true
      text: root.source ? String(root.source.scope || "user") + " · " + String(root.source.format || "unknown") + " · " + String(root.source.status || "unknown") : ""
      color: Qt.alpha(root.foreground, 0.7)
      font.family: Style.font.family
      font.pixelSize: Style.font.caption
      elide: Text.ElideRight
    }
  }
}
