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
  Layout.preferredHeight: Style.space(54)
  text: agent ? String(agent.name || "Agent") + (agent.isOmarchyDefault ? " · Default" : (agent.support === "read-write" ? " · Ready" : " · View")) : "Agent"
  activeFocusOnTab: true
  hasCursor: selected
  onClicked: root.chosen()

}
