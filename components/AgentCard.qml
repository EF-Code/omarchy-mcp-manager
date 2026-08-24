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
  text: agent ? String(agent.name || "Agent") : "Agent"
  activeFocusOnTab: true
  hasCursor: selected
  onClicked: root.chosen()

  contentItem: RowLayout {
    spacing: Style.space(8)
    Text {
      text: root.agent && root.agent.isOmarchyDefault ? "◆" : "○"
      color: root.agent && root.agent.isOmarchyDefault ? Color.accent : root.foreground
      font.pixelSize: Style.font.body
    }
    Text {
      Layout.fillWidth: true
      text: root.agent ? String(root.agent.name || "Agent") : "Agent"
      color: root.foreground
      font.family: Style.font.family
      font.pixelSize: Style.font.body
      elide: Text.ElideRight
    }
    Text {
      text: root.agent && root.agent.isOmarchyDefault ? "Default" : (root.agent && root.agent.support === "read-write" ? "Ready" : "View")
      color: root.agent && root.agent.isOmarchyDefault ? Color.accent : Qt.alpha(root.foreground, 0.7)
      font.family: Style.font.family
      font.pixelSize: Style.font.caption
    }
  }
}
