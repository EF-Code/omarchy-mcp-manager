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
  Layout.minimumWidth: 0
  Layout.preferredHeight: Style.space(48)
  Layout.maximumHeight: Style.space(48)
  verticalPadding: Style.space(4)
  hasCursor: selected
  activeFocusOnTab: true
  text: root.source ? String(root.source.pathDisplay || "Source") + " · " + String(root.source.scope || "user") + " · " + String(root.source.status || "unknown") : "Source"
  tooltipText: text
  leftAlign: true
  clip: true
  onClicked: root.chosen()
}
