import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui

Button {
  id: root
  property var server: null
  property bool selected: false
  property color foreground: Color.foreground
  signal editRequested()
  signal toggleRequested()
  signal removeRequested()
  Layout.fillWidth: true
  Layout.minimumWidth: 0
  Layout.preferredHeight: Style.space(56)
  hasCursor: selected
  activeFocusOnTab: true
  text: root.server ? String(root.server.name || "Server") + " · " + String(root.server.transport || "unknown").toUpperCase() + " · " + (root.server.enabled ? "Enabled" : "Disabled") + (root.server.command ? " · " + String(root.server.command) : "") : "Server"
  tooltipText: text
  leftAlign: true
  clip: true
  onClicked: root.editRequested()
}
