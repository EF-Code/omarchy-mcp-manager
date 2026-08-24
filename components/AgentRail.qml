import QtQuick
import QtQuick.Layouts
import qs.Commons

Flickable {
  id: root
  property var agents: []
  property int selectedIndex: 0
  property color foreground: Color.foreground
  signal selected(int index)
  Layout.preferredHeight: Style.space(270)
  clip: true
  contentWidth: width
  contentHeight: railColumn.implicitHeight
  boundsBehavior: Flickable.StopAtBounds

  ColumnLayout {
    id: railColumn
    width: root.width
    spacing: Style.space(4)
    Repeater {
      model: root.agents
      AgentCard {
        required property var modelData
        required property int index
        agent: modelData
        selected: index === root.selectedIndex
        foreground: root.foreground
        onChosen: root.selected(index)
      }
    }
  }
}
