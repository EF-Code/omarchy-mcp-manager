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
  Layout.preferredHeight: Style.space(70)
  hasCursor: selected
  activeFocusOnTab: true
  text: root.server ? String(root.server.name || "Server") + " · " + String(root.server.transport || "unknown").toUpperCase() + " · " + (root.server.enabled ? "Enabled" : "Disabled") + (root.server.command ? " · " + String(root.server.command) : "") : "Server"
  onClicked: root.editRequested()
}
