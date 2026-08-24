import QtQuick
import QtQuick.Layouts
import qs.Commons

ColumnLayout {
  id: root
  property var agents: []
  property int selectedIndex: 0
  property color foreground: Color.foreground
  signal selected(int index)
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
