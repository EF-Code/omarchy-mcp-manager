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
  text: root.source ? String(root.source.pathDisplay || "Source") + " · " + String(root.source.scope || "user") + " · " + String(root.source.status || "unknown") : "Source"
  onClicked: root.chosen()
}
