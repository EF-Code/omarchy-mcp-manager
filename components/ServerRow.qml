import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui

Button {
  id: root
  property var server: null
  signal chosen()
  Layout.fillWidth: true
  Layout.minimumWidth: 0
  Layout.preferredHeight: Style.space(56)
  bordered: true
  background: Qt.alpha(root.foreground, 0.025)
  hasCursor: selected
  focusable: true
  text: root.server ? String(root.server.name || "Server") + " · " + String(root.server.transport || "unknown").toUpperCase() + " · " + (root.server.enabled ? "Enabled" : "Disabled") + (root.server.command ? " · " + String(root.server.command) : "") : "Server"
  tooltipText: text
  leftAlign: true
  clip: true
  onClicked: root.chosen()
}
