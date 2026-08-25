import QtQuick
import QtQuick.Layouts
import qs.Commons
import qs.Ui

Button {
  id: root
  property var agent: null
  property bool selected: false
  property color foreground: Color.foreground
  signal chosen()
  Layout.fillWidth: true
  Layout.minimumWidth: 0
  Layout.preferredHeight: Style.space(46)
  Layout.maximumHeight: Style.space(46)
  verticalPadding: Style.space(4)
  text: agent ? String(agent.name || "Agent") + (agent.isOmarchyDefault ? " · Default" : (agent.support === "read-write" ? " · Ready" : " · View")) : "Agent"
  tooltipText: text
  leftAlign: true
  clip: true
  activeFocusOnTab: true
  hasCursor: selected
  onClicked: root.chosen()
}
